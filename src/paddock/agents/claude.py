from pathlib import Path

from paddock.agents import BaseAgent
from paddock.config.filters import VolumeSpec


class ClaudeAgent(BaseAgent):
    AGENT_KEY = "claude"

    def get_command(self) -> list[str]:
        return ["claude"]

    def get_volumes(self) -> dict[str, VolumeSpec]:
        return {str(Path.home() / ".claude"): VolumeSpec("/root/.claude", "rw")}

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "claude"}
