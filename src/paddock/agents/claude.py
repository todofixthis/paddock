from pathlib import Path

from paddock.agents import BaseAgent


class ClaudeAgent(BaseAgent):
    AGENT_KEY = "claude"

    def get_command(self) -> list[str]:
        return ["claude"]

    def get_volumes(self) -> dict[str, str]:
        return {str(Path.home() / ".claude"): "/root/.claude:rw"}

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "claude"}
