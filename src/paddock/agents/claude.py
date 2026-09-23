from pathlib import Path

from paddock.agents import BaseAgent
from paddock.config.filters import VolumeSpec


class ClaudeAgent(BaseAgent):
    AGENT_KEY = "claude"

    def get_command(self) -> list[str]:
        return ["claude"]

    def get_volumes(self) -> dict[str, VolumeSpec]:
        """Mount Claude Code's config directory and global config file.

        Claude Code keeps onboarding and account state in ``~/.claude.json``,
        beside ``~/.claude`` rather than inside it; without it every run
        starts with onboarding.

        Note:
            ``~/.claude.json`` is mounted only when it is a file. A missing
            path would reach ``docker run -v``, which creates it as a
            directory and breaks the host's Claude Code; a directory is no
            config file to mount. Without it, runs still start at
            onboarding.

            Claude Code saves this file by temp file + rename, which fails
            with ``EBUSY`` on a single-file bind mount; Claude Code falls
            back to writing in place. If a release drops that fallback,
            this mount stops persisting anything.

            The mount pins the file's inode, and the host's Claude Code
            renames a new file into place on each save. A container
            running at the time keeps the old inode: it reads stale state
            and its later writes are lost.
        """
        home = Path.home()
        volumes = {str(home / ".claude"): VolumeSpec("/root/.claude", "rw")}
        claude_json = home / ".claude.json"
        if claude_json.is_file():
            volumes[str(claude_json)] = VolumeSpec("/root/.claude.json", "rw")
        return volumes

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "claude"}
