import re
import subprocess
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path
from typing import Any

from paddock.agents import BaseAgent
from paddock.agents.servers import ServerConnection
from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec
from paddock.docker.environment import ContainerEnvironment

# Network modes Docker cannot combine with a second network.
_UNCOMBINABLE_NETWORKS = frozenset({"bridge", "default", "host", "none"})


def sanitise_volume_name(image: str, agent_key: str) -> str:
    """Generate a Docker volume name from image + agent key."""
    sanitised = re.sub(r"[^a-z0-9]", "_", image.lower())
    return f"paddock_{sanitised}_{agent_key}"


class DockerCommandBuilder:
    def __init__(
        self,
        *,
        config: dict[str, Any],
        agent: BaseAgent,
        workdir: Path,
        project_dir_volume: tuple[str, VolumeSpec] | None = None,
        connection: ServerConnection | None = None,
    ) -> None:
        """Initialises the builder with config, agent, workdir, and optional project dir.

        Args:
            config: The resolved configuration dict.
            agent: The agent instance providing volumes and commands.
            workdir: The project working directory to mount.
            project_dir_volume: Optional ``(host_path, VolumeSpec)`` pair for
                the ``.paddock`` bind-mount. Emitted after the workdir volume.
            connection: The server the client is paired with, or ``None``.
                A client merely chosen beside a server gets none.
        """
        self._config = config
        self._agent = agent
        self._workdir = workdir
        self._project_dir_volume = project_dir_volume
        self._connection = connection

    def build(self, *, command: list[str], agent_args: Sequence[str] = ()) -> list[str]:
        """Assemble the full 'docker run' argv list.

        Args:
            command: Replaces the agent's command when non-empty.
            agent_args: Appended to the agent's command; ignored when
                ``command`` replaces it.
        """
        argv = ["docker", "run", "--rm", "-it"]
        argv += ["--name", self._resolve_container_name()]
        argv += [f"--workdir={self._workdir}"]
        for host_or_name, container_spec in self.volumes:
            argv += self._volume_flag(host_or_name, container_spec)
        for network in self._networks():
            argv += ["--network", network]
        argv += self.environment.flags()
        argv.append(self._config["image"])
        argv += command if command else [*self._agent_command(), *agent_args]
        return argv

    @cached_property
    def environment(self) -> ContainerEnvironment:
        """The environment variables that connect the client to its server.

        ``docker run`` must be given the secret ones in its own environment.
        Empty for a client that is not paired with a server.
        """
        if self._connection is None:
            return ContainerEnvironment({})
        return ContainerEnvironment(
            self._agent.get_server_env(self._connection),
            secret=self._connection.secret,
        )

    @staticmethod
    def check_paired_network(
        network: str | None, *, agent_key: str, server_key: str
    ) -> None:
        """Refuse a configured network a paired client cannot keep.

        A paired client joins its server's network as well as its own, and
        Docker cannot combine these modes with a second network.

        Args:
            network: The configured ``network``, or ``None``.
            agent_key: The paired client's registry key.
            server_key: The server's registry key.

        Raises:
            PaddockEnvironmentError: If the network cannot be combined.
        """
        if network is None:
            return
        if network in _UNCOMBINABLE_NETWORKS or network.startswith("container:"):
            raise PaddockEnvironmentError(
                f'[network] "{network}" cannot be combined with a server\'s '
                f'network; agent "{agent_key}" is paired with server '
                f'"{server_key}"'
            )

    def _networks(self) -> list[str]:
        """The networks the container joins: configured, then the server's."""
        networks = []
        if self._config.get("network"):
            networks.append(self._config["network"])
        if self._connection is not None and self._connection.network not in networks:
            networks.append(self._connection.network)
        return networks

    def _agent_command(self) -> list[str]:
        """The agent's command, pointed at its server where it has one."""
        command = list(self._agent.get_command())
        if self._connection is not None:
            command += self._agent.get_server_args(self._connection)
        return command

    @cached_property
    def volumes(self) -> list[tuple[str, VolumeSpec]]:
        """List every volume the container mounts, in ``-v`` flag order.

        The single source for both :meth:`build` and the "Mounting" log, so
        the log cannot drift from what the container actually mounts.
        Cached so both see one snapshot: agent volumes probe the filesystem,
        and an image build can run between the log and :meth:`build`.

        Returns:
            ``(host_path_or_volume_name, VolumeSpec)`` pairs: the workdir,
            then the ``.paddock`` directory, agent volumes, config volumes
            and agent scratch volumes.
        """
        volumes = [(str(self._workdir), VolumeSpec(str(self._workdir), "rw"))]
        if self._project_dir_volume is not None:
            volumes.append(self._project_dir_volume)
        volumes += self._agent.get_volumes().items()
        volumes += self._config.get("volumes", {}).items()
        volumes += self._agent.get_scratch_volumes(self._config["image"]).items()
        return volumes

    def _resolve_container_name(self) -> str:
        """Derive container name from workdir; append numeric suffix if taken."""
        dirname = self._workdir.name.lower()
        agent_key = self._agent.AGENT_KEY
        base_name = f"paddock-{dirname}-{agent_key}"
        if self._container_name_available(base_name):
            return base_name
        suffix = 1
        while True:
            candidate = f"{base_name}-{suffix}"
            if self._container_name_available(candidate):
                return candidate
            suffix += 1

    def _container_name_available(self, name: str) -> bool:
        """Return True if no running or stopped container has this name."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format={{.Names}}"],
            capture_output=True,
            text=True,
        )
        return name not in result.stdout.splitlines()

    @staticmethod
    def _volume_flag(host_or_name: str, container_spec: VolumeSpec) -> list[str]:
        return ["-v", f"{host_or_name}:{container_spec}"]
