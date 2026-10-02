import re
import subprocess
from collections.abc import Sequence
from pathlib import Path

from paddock.agents import BaseAgent
from paddock.config.filters import VolumeSpec


def sanitise_volume_name(image: str, agent_key: str) -> str:
    """Generate a Docker volume name from image + agent key."""
    sanitised = re.sub(r"[^a-z0-9]", "_", image.lower())
    return f"paddock_{sanitised}_{agent_key}"


class DockerCommandBuilder:
    def __init__(
        self,
        *,
        config: dict,
        agent: BaseAgent,
        workdir: Path,
        project_dir_volume: tuple[str, VolumeSpec] | None = None,
    ) -> None:
        """Initialises the builder with config, agent, workdir, and optional project dir.

        Args:
            config: The resolved configuration dict.
            agent: The agent instance providing volumes and commands.
            workdir: The project working directory to mount.
            project_dir_volume: Optional ``(host_path, VolumeSpec)`` pair for
                the ``.paddock`` bind-mount. Emitted after the workdir volume.
        """
        self._config = config
        self._agent = agent
        self._workdir = workdir
        self._project_dir_volume = project_dir_volume

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
        for host_or_name, container_spec in self.volumes():
            argv += self._volume_flag(host_or_name, container_spec)
        if self._config.get("network"):
            argv += ["--network", self._config["network"]]
        argv.append(self._config["image"])
        argv += command if command else [*self._agent.get_command(), *agent_args]
        return argv

    def volumes(self) -> list[tuple[str, VolumeSpec]]:
        """List every volume the container mounts, in ``-v`` flag order.

        The single source for both :meth:`build` and the "Mounting" log, so
        the log cannot drift from what the container actually mounts.

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
