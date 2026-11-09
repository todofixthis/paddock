from collections.abc import Mapping
from os import environ
from pathlib import Path

from paddock.agents import BaseAgent
from paddock.config.filters import VolumeSpec


class OpenCodeAgent(BaseAgent):
    AGENT_KEY = "opencode"

    def get_command(self) -> list[str]:
        return ["opencode"]

    def get_volumes(self) -> dict[str, VolumeSpec]:
        """Mount OpenCode's config and data directories.

        OpenCode keeps settings in ``$XDG_CONFIG_HOME/opencode`` and its
        database, sign-in included, in ``$XDG_DATA_HOME/opencode``. Each
        mounts at its XDG default under ``/root``, where OpenCode looks in a
        container that sets no XDG variables.

        Note:
            Each directory is mounted only when it exists. A missing path
            would reach ``docker run -v``, which creates it owned by root on
            Linux and locks the host's OpenCode out of it. Without the mount,
            everything OpenCode writes there in the container, sign-in
            included, is lost when it exits.

            ``$XDG_STATE_HOME/opencode`` is not mounted: it registers the
            host's background service by address, which the container
            cannot reach. Without it, the container keeps its own config
            file locks, so OpenCode on the host and in the container can
            race when both save config at once.
        """
        volumes = {}
        for name, default in (
            ("XDG_CONFIG_HOME", ".config"),
            ("XDG_DATA_HOME", ".local/share"),
        ):
            host_dir = self._xdg_home(environ, name, default) / "opencode"
            if host_dir.is_dir():
                volumes[str(host_dir)] = VolumeSpec(f"/root/{default}/opencode", "rw")
        return volumes

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "opencode"}

    @staticmethod
    def _xdg_home(env: Mapping[str, str], name: str, default: str) -> Path:
        """Resolve an XDG base directory as OpenCode does on the host.

        Args:
            env: Environment variable mapping to read ``name`` from.
            name: The XDG variable, e.g. ``'XDG_DATA_HOME'``.
            default: The fallback, relative to the home directory.

        Returns:
            The variable's value, or ``~/<default>`` where it is unset or
            empty, made absolute against the current directory as
            OpenCode would resolve a relative value.
        """
        return Path(env.get(name) or Path.home() / default).absolute()
