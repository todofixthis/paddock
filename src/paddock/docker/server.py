import secrets
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from paddock.agents.servers import BaseServer, ServerConnection
from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec
from paddock.config.server_settings import ServerSettings
from paddock.docker.factory import ImageSourceFactory
from paddock.docker.managed import (
    SPEC_HASH_LABEL,
    ContainerSpec,
    ContainerState,
    ContainerStatus,
    ManagedContainer,
)

# Holds the secret in every server's environment, whatever the server's own
# variable is called, so paddock can read it back without asking the class.
SECRET_ENV = "PADDOCK_SERVER_SECRET"

Mounts = list[tuple[str, VolumeSpec]]


@dataclass(frozen=True)
class LaunchResult:
    """What launching a server found or did."""

    connection: ServerConnection
    """How a client reaches the server."""

    created: bool
    """Whether this run created the container."""

    drifted: bool
    """Whether a container this run did not create differs from config."""

    run_argv: list[str] | None
    """The ``docker run`` line this run used, or under a dry run would."""


class ServerLauncher:
    """Starts a server's shared container, or finds it running (ADR 019).

    Paddock never stops, restarts or force-removes a server: a stopped one is
    removed and recreated, a running one is used as it is, and a difference
    from config is reported, not acted on.
    """

    POLLS = 60
    POLL_INTERVAL = 0.5

    # Stand in for values a dry run does not have.
    _NO_SECRET = "<secret>"
    _NO_PORT = "<port>"

    _LIVE = (ContainerState.RUNNING, ContainerState.STARTING)

    def __init__(
        self,
        server: BaseServer,
        settings: ServerSettings,
        *,
        environ: Mapping[str, str],
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialises the launcher; nothing is run.

        Args:
            server: The server to start.
            settings: Its settings, checked on disk.
            environ: Environment variable mapping, for the pull log's path.
            sleep: Waits between readiness polls.
        """
        self._server = server
        self._settings = settings
        self._environ = environ
        self._sleep = sleep
        self._key = server.SERVER_KEY
        self._name = f"paddock-server-{self._key}"

    def launch(self, *, workdir: Path | None, dry_run: bool) -> LaunchResult:
        """Make the server available, creating its container if needed.

        Every check runs before anything is created.

        Args:
            workdir: The workdir the server must have mounted, for a paired
                client and a server that runs tools in the project; ``None``
                skips that check.
            dry_run: Run every check, but create, build, pull, remove and
                mint nothing.

        Returns:
            The connection and what was done to get it.

        Raises:
            PaddockEnvironmentError: If the server cannot be used.
        """
        container = ManagedContainer(self._spec(self._NO_SECRET))
        status = self._owned(container.status())
        live = status.state in self._LIVE
        spec = self._spec(self._NO_SECRET if live or dry_run else self._mint())
        container = ManagedContainer(spec)

        if workdir is not None:
            mounts = (
                ManagedContainer.volumes_from_labels(status.labels)
                if live
                else spec.volumes
            )
            self._check_workdir(workdir, mounts, live)
        container.check_network()

        if dry_run:
            return self._dry_run_result(container, spec, status)

        created = False
        if not live:
            created = self._create(container, status)
        connection, status = self._wait(container, status)
        return LaunchResult(
            connection=connection,
            created=created,
            drifted=not created and self._drifted(status, spec),
            run_argv=spec.run_argv() if created else None,
        )

    def _spec(self, secret: str) -> ContainerSpec:
        """Build the container's spec around one secret.

        The environment's names must not depend on the secret, or every reuse
        would read as drift.

        Args:
            secret: The secret to start the server with, or a placeholder.
        """
        return ContainerSpec(
            name=self._name,
            owner=f"server:{self._key}",
            image=self._settings.image,
            command=self._server.get_command(),
            env={**self._server.get_env(secret), SECRET_ENV: secret},
            volumes=[
                *self._server.get_volumes().items(),
                *self._settings.volumes.items(),
                *self._server.get_scratch_volumes().items(),
            ],
            container_port=self._server.CONTAINER_PORT,
            host_port=self._settings.port,
        )

    def _mint(self) -> str:
        """Mint the secret a new server container is started with."""
        return secrets.token_urlsafe(32)

    def _owned(self, status: ContainerStatus) -> ContainerStatus:
        """Refuse a container of the server's name that is not paddock's.

        Args:
            status: A reading of the container.

        Returns:
            The same status.

        Raises:
            PaddockEnvironmentError: If the container is foreign.
        """
        if status.state is ContainerState.FOREIGN:
            raise PaddockEnvironmentError(
                f'[agent.server] A container named "{self._name}" exists that '
                "paddock did not create; remove or rename it"
            )
        return status

    def _check_workdir(self, workdir: Path, mounts: Mounts, live: bool) -> None:
        """Require the workdir under a read-write mount at its own path.

        The mount that counts is the most specific one covering the workdir:
        a broader mount it shadows does not reach the server. Paths are
        compared whole, never as strings.

        Args:
            workdir: The run's workdir.
            mounts: The server's mounts: a live container's own, read from
                its label, or the ones a new container would get.
            live: Whether a container holds those mounts now, so that a new
                mount needs it recreated.

        Raises:
            PaddockEnvironmentError: If no such mount covers the workdir.
        """
        target = PurePosixPath(workdir)
        covering: tuple[str, VolumeSpec] | None = None
        for source, spec in mounts:
            path = PurePosixPath(spec.container_path)
            if path != target and path not in target.parents:
                continue
            if covering is None or len(path.parts) > len(
                PurePosixPath(covering[1].container_path).parts
            ):
                covering = (source, spec)

        if covering is not None:
            source, spec = covering
            # A named volume has no leading slash, so it never equals a path.
            same_path = PurePosixPath(source) == PurePosixPath(spec.container_path)
            if spec.mode == "rw" and source.startswith("/") and same_path:
                return

        listed = ", ".join(sorted(f"{s}:{spec}" for s, spec in mounts)) or "none"
        message = (
            f'[agent.server] Server "{self._key}" does not have {workdir} '
            f"mounted read-write at the same path; its mounts: {listed}. Add a "
            f"mount under [agents.{self._key}.server.volumes] in your user config"
        )
        if live:
            message += f", then recreate the server: docker rm -f {self._name}"
        raise PaddockEnvironmentError(message)

    def _dry_run_result(
        self, container: ManagedContainer, spec: ContainerSpec, status: ContainerStatus
    ) -> LaunchResult:
        """Describe what a real launch would find or do, changing nothing.

        Args:
            container: The server's container.
            spec: The spec a new container would get.
            status: The reading taken at the start of the launch.
        """
        secret: str = self._NO_SECRET
        port: int | str | None = None
        if status.state is ContainerState.RUNNING:
            secret = self._secret(status)
            port = container.published_port()
        if port is None:
            port = self._settings.port or self._NO_PORT
        live = status.state in self._LIVE
        return LaunchResult(
            connection=self._connection(port, secret),
            created=False,
            drifted=live and self._drifted(status, spec),
            run_argv=None if live else spec.run_argv(),
        )

    def _create(self, container: ManagedContainer, status: ContainerStatus) -> bool:
        """Replace a stopped container, or create a missing one.

        Args:
            container: The server's container.
            status: The reading that found it missing or stopped.

        Returns:
            Whether this run created it; ``False`` if another took the name.

        Raises:
            PaddockEnvironmentError: If the image or the container failed.
        """
        # The image first: if it fails, a stopped container keeps its logs.
        if self._settings.build is not None:
            self._prepare_image(self._settings.build)
        if status.container_id is not None:
            container.remove_stopped(status.container_id)
        return container.start()

    def _prepare_image(self, build: dict) -> None:
        """Build or pull the server's image under its ``build`` settings.

        Docker's own output is the report.

        Args:
            build: The server's ``build`` settings.

        Raises:
            PaddockEnvironmentError: If Docker failed.
        """
        source = ImageSourceFactory.from_config(
            build,
            agent_build_args=self._server.get_build_args(),
            environ=self._environ,
        )
        try:
            source.refresh(self._settings.image)
        except subprocess.CalledProcessError as error:
            raise PaddockEnvironmentError(
                "[agent.server] Could not build or pull the image for server "
                f'"{self._key}": docker exited {error.returncode}'
            ) from error

    def _wait(
        self, container: ManagedContainer, status: ContainerStatus
    ) -> tuple[ServerConnection, ContainerStatus]:
        """Poll until the server is ready, whoever started it.

        Args:
            container: The server's container.
            status: The latest reading, replaced by each poll's own.

        Returns:
            The connection, and the reading it was made from.

        Raises:
            PaddockEnvironmentError: If the container stops, is not paddock's,
                or is not ready when the polls run out.
        """
        for _ in range(self.POLLS):
            status = self._owned(container.status())
            if status.state in (ContainerState.MISSING, ContainerState.STOPPED):
                raise PaddockEnvironmentError(
                    f'[agent.server] Server "{self._key}" stopped while '
                    f"starting; see: docker logs {self._name}"
                )
            if status.state is ContainerState.RUNNING:
                secret = self._secret(status)
                port = container.published_port()
                if port is not None:
                    connection = self._connection(port, secret)
                    if self._server.is_ready(connection):
                        return connection, status
            self._sleep(self.POLL_INTERVAL)

        if status.state is ContainerState.STARTING and status.container_id:
            # Abandoned between create and start. Without -f, this fails
            # harmlessly if it has started since.
            container.remove_stopped(status.container_id)
            raise PaddockEnvironmentError(
                f'[agent.server] Server "{self._key}" was created but never '
                "started; it has been removed, so run again"
            )
        raise PaddockEnvironmentError(
            f'[agent.server] Server "{self._key}" was not ready after '
            f"{self.POLLS * self.POLL_INTERVAL:g} seconds; see: docker logs "
            f"{self._name}"
        )

    def _secret(self, status: ContainerStatus) -> str:
        """Read a running server's secret back from its environment.

        Args:
            status: A reading of the running container.

        Raises:
            PaddockEnvironmentError: If it holds none.
        """
        secret = status.env.get(SECRET_ENV)
        if not secret:
            raise PaddockEnvironmentError(
                f'[agent.server] Server "{self._key}" is running without a '
                "secret paddock can read; to recreate it: docker rm -f "
                f"{self._name}"
            )
        return secret

    def _drifted(self, status: ContainerStatus, spec: ContainerSpec) -> bool:
        """Whether a container was created from a spec other than ``spec``."""
        return status.labels.get(SPEC_HASH_LABEL) != spec.spec_hash()

    def _connection(self, port: int | str, secret: str) -> ServerConnection:
        """Describe how a client reaches the server.

        Args:
            port: The loopback port the server is published on.
            secret: The server's secret.
        """
        return ServerConnection(
            container_url=f"http://{self._name}:{self._server.CONTAINER_PORT}",
            host_url=f"http://127.0.0.1:{port}",
            network=self._name,
            secret=secret,
        )
