from paddock.agents import BaseAgent


class ShellAgent(BaseAgent):
    AGENT_KEY = "false"

    def get_command(self) -> list[str]:
        return ["/bin/bash"]

    def get_volumes(self) -> dict[str, str]:
        return {}

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "none"}
