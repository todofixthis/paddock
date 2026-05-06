import re
import subprocess
from pathlib import Path

from paddock.agents import BaseAgent


def sanitise_volume_name(image: str, agent_key: str) -> str:
    """Generate a Docker volume name from image + agent key."""
    sanitised = re.sub(r"[^a-z0-9]", "_", image.lower())
    return f"paddock_{sanitised}_{agent_key}"


class DockerCommandBuilder:
    def __init__(self, *, config: dict, agent: BaseAgent, workdir: Path) -> None:
        self._config = config
        self._agent = agent
        self._workdir = workdir

    def build(self, *, command: list[str]) -> list[str]:
        """Assemble the full 'docker run' argv list."""
        argv = ["docker", "run", "--rm", "-it"]
        argv += ["--name", self._resolve_container_name()]
        argv += [f"--workdir={self._workdir}"]
        argv += self._volume_flag(str(self._workdir), f"{self._workdir}:rw")
        for host, container in self._agent.get_volumes().items():
            argv += self._volume_flag(host, container)
        for host, container in self._config.get("volumes", {}).items():
            argv += self._volume_flag(host, container)
        for vol_name, container_path in self._agent.get_scratch_volumes(
            self._config["image"]
        ).items():
            argv += self._volume_flag(vol_name, container_path)
        if self._config.get("network"):
            argv += ["--network", self._config["network"]]
        argv.append(self._config["image"])
        argv += command if command else self._agent.get_command()
        return argv

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
    def _volume_flag(host_or_name: str, container_spec: str) -> list[str]:
        return ["-v", f"{host_or_name}:{container_spec}"]
