import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field
from enum import Enum

from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec

MANAGED_LABEL = "paddock.managed"
SPEC_HASH_LABEL = "paddock.spec-hash"
VOLUMES_LABEL = "paddock.volumes"


@dataclass(frozen=True)
class ContainerSpec:
    """How one managed container is run."""

    name: str
    """The container's name, and its network's."""

    owner: str
    """The ``paddock.managed`` label's value, e.g. ``server:opencode``."""

    image: str
    """The image reference to run."""

    command: list[str]
    """The command to run in the container."""

    env: dict[str, str] = field(repr=False)
    """Environment variables; the values may be secret."""

    volumes: list[tuple[str, VolumeSpec]]
    """Mounts, each from a host path or a named volume."""

    container_port: int
    """The port the container listens on."""

    host_port: int | None
    """The loopback port to publish it on, or ``None`` for Docker's choice."""

    def spec_hash(self) -> str:
        """Hash everything a changed setting would alter.

        Environment variables count by name only, so a new secret is not
        drift; volumes are sorted, so reordering config is not either.
        """
        canonical = json.dumps(
            {
                "command": self.command,
                "container_port": self.container_port,
                "env": sorted(self.env),
                "host_port": self.host_port,
                "image": self.image,
                "volumes": self._sorted_volumes(),
            },
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def run_argv(self) -> list[str]:
        """Assemble the ``docker run`` argv.

        Environment variables are passed by name, so no value appears in it:
        the caller supplies the values in the subprocess environment.
        """
        argv = ["docker", "run", "-d", "--name", self.name, "--network", self.name]
        argv += ["--label", f"{MANAGED_LABEL}={self.owner}"]
        argv += ["--label", f"{SPEC_HASH_LABEL}={self.spec_hash()}"]
        argv += ["--label", f"{VOLUMES_LABEL}={json.dumps(self._sorted_volumes())}"]
        host_port = "" if self.host_port is None else self.host_port
        argv += ["-p", f"127.0.0.1:{host_port}:{self.container_port}"]
        for name in sorted(self.env):
            argv += ["-e", name]
        for source, spec in self.volumes:
            argv += ["-v", f"{source}:{spec}"]
        return [*argv, self.image, *self.command]

    def _sorted_volumes(self) -> list[list[str]]:
        """The volumes as sorted ``[source, spec]`` pairs, for JSON."""
        return sorted([source, str(spec)] for source, spec in self.volumes)


class ContainerState(Enum):
    """What a managed container's name currently refers to."""

    MISSING = "missing"
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    FOREIGN = "foreign"


@dataclass(frozen=True)
class ContainerStatus:
    """One reading of a managed container."""

    state: ContainerState
    """What the name refers to."""

    container_id: str | None
    """The container's ID, or ``None`` when missing."""

    env: dict[str, str] = field(repr=False)
    """The container's environment; the values may be secret."""

    labels: dict[str, str]
    """The container's labels."""


class ManagedContainer:
    """One named, labelled, long-lived container on a network of its own.

    It knows nothing about agents: the owner label is all that ties it to
    whatever it serves. Paddock never stops or force-removes one (ADR 019).
    """

    # Docker's stderr for a name already taken. A port conflict also says
    # "already in use", so match on this and nothing shorter.
    _NAME_CONFLICT = "Conflict. The container name"

    def __init__(self, spec: ContainerSpec) -> None:
        """Initialises the container from its spec; nothing is run.

        Args:
            spec: How the container is, or would be, run.
        """
        self._spec = spec

    def status(self) -> ContainerStatus:
        """Read the container's state with one ``docker container inspect``.

        The container and its network share a name, and plain
        ``docker inspect`` would return the network once the container is
        gone.
        """
        entry = self._inspect("container")
        if entry is None:
            return ContainerStatus(ContainerState.MISSING, None, {}, {})

        labels = entry["Config"].get("Labels") or {}
        env = {}
        for item in entry["Config"].get("Env") or []:
            name, _, value = item.partition("=")
            env[name] = value
        return ContainerStatus(
            self._state(entry["State"], labels), entry["Id"], env, labels
        )

    def check_network(self) -> None:
        """Refuse a network of this name that paddock did not create.

        Raises:
            PaddockEnvironmentError: If one exists without the owner label.
        """
        self._network_exists()

    def start(self) -> bool:
        """Create the network if it is missing, then run the container.

        Returns:
            ``True`` if this call created the container; ``False`` if another
            process took the name first, which is not an error.

        Raises:
            PaddockEnvironmentError: If the network is not paddock's, or
                Docker could not create the network or start the container.
        """
        if not self._network_exists():
            self._create_network()

        result = subprocess.run(
            self._spec.run_argv(),
            capture_output=True,
            env={**os.environ, **self._spec.env},
            text=True,
        )
        if result.returncode == 0:
            return True
        if self._NAME_CONFLICT in result.stderr:
            return False
        raise self._could_not_start(result.stderr)

    def remove_stopped(self, container_id: str) -> None:
        """Remove a container that is not running, by the ID observed.

        Without ``-f``, so one that has started since is left alone; a failure
        means another process got there first, and is ignored.

        Args:
            container_id: The ID a status reading reported.
        """
        subprocess.run(["docker", "rm", container_id], capture_output=True, text=True)

    def published_port(self) -> int | None:
        """Read the loopback port the container's port is published on.

        Returns:
            The port, or ``None`` when Docker reports none, as it does for a
            container that is not running.
        """
        result = subprocess.run(
            ["docker", "port", self._spec.name, f"{self._spec.container_port}/tcp"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.split()
        if result.returncode != 0 or not lines:
            return None
        return int(lines[0].rpartition(":")[2])

    @staticmethod
    def volumes_from_labels(labels: dict[str, str]) -> list[tuple[str, VolumeSpec]]:
        """Read back the mounts a container was created with.

        Args:
            labels: The container's labels.

        Returns:
            The mounts, sorted; empty where the label is absent.
        """
        volumes = []
        for source, spec in json.loads(labels.get(VOLUMES_LABEL, "[]")):
            container_path, _, mode = spec.rpartition(":")
            volumes.append((source, VolumeSpec(container_path, mode)))
        return volumes

    def _state(self, state: dict, labels: dict[str, str]) -> ContainerState:
        """Classify an inspected container.

        Args:
            state: The container's ``.State``.
            labels: The container's labels.
        """
        if labels.get(MANAGED_LABEL) != self._spec.owner:
            return ContainerState.FOREIGN
        if state.get("Running"):
            return ContainerState.RUNNING
        # ``docker run`` creates, then starts: in between, the container is
        # ``created`` with no error. One that failed to start keeps an error.
        if state.get("Status") == "created" and not state.get("Error"):
            return ContainerState.STARTING
        return ContainerState.STOPPED

    def _network_exists(self) -> bool:
        """Report whether paddock's network of this name exists.

        Raises:
            PaddockEnvironmentError: If one exists without the owner label.
        """
        entry = self._inspect("network")
        if entry is None:
            return False
        if (entry.get("Labels") or {}).get(MANAGED_LABEL) != self._spec.owner:
            raise PaddockEnvironmentError(
                f'[docker] A network named "{self._spec.name}" exists that '
                "paddock did not create; remove or rename it"
            )
        return True

    def _create_network(self) -> None:
        """Create the network, tolerating another process creating it first.

        Raises:
            PaddockEnvironmentError: If it could not be created and does not
                exist, or exists without the owner label.
        """
        result = subprocess.run(
            [
                "docker",
                "network",
                "create",
                "--label",
                f"{MANAGED_LABEL}={self._spec.owner}",
                self._spec.name,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 and not self._network_exists():
            raise self._could_not_start(result.stderr)

    def _inspect(self, kind: str) -> dict | None:
        """Inspect the container or the network of this name.

        Args:
            kind: ``container`` or ``network``.

        Returns:
            The object's inspect entry, or ``None`` where none exists.
        """
        result = subprocess.run(
            ["docker", kind, "inspect", self._spec.name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)[0]

    def _could_not_start(self, stderr: str) -> PaddockEnvironmentError:
        """Build the error for a Docker failure, from its first line.

        Args:
            stderr: Docker's standard error.
        """
        lines = [line.strip() for line in stderr.splitlines() if line.strip()]
        reason = lines[0] if lines else "docker gave no reason"
        return PaddockEnvironmentError(
            f'[docker] Could not start "{self._spec.name}": {reason}'
        )
