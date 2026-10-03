from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from paddock.cli import ParsedArgs


@dataclass(frozen=True)
class ConfigContext:
    """All inputs any :class:`ConfigSource` might need to load itself.

    A single immutable object is constructed once per resolve and passed to
    every source. Sources pick whatever fields they need from it.

    Attributes:
        parsed: Parsed CLI arguments.
        environ: Process environment mapping. Should be a copy — sources may
            read from it but must not mutate.
        workdir: Resolved working directory (a real path on disk).
        user_config_path: Path to the user config file. May not exist on disk;
            sources are responsible for handling missing files gracefully.
    """

    parsed: ParsedArgs
    environ: dict[str, str]
    workdir: Path
    user_config_path: Path

    @property
    def project_key(self) -> str:
        """Absolute resolved workdir as a string — the lookup key under ``[projects]``.

        Plain ``@property`` rather than ``@cached_property``: caching needs
        writable instance state, which ``frozen=True`` forbids. The computation
        is a single ``Path.resolve()`` call — cheap enough to repeat.
        """
        return str(self.workdir.resolve())

    @staticmethod
    def default_user_config_path(environ: Mapping[str, str]) -> Path:
        """Return the user config path, ``$XDG_CONFIG_HOME/paddock/config.toml``.

        Follows the XDG Base Directory spec: an unset or empty
        ``XDG_CONFIG_HOME`` falls back to ``~/.config``, and a relative one is
        invalid and ignored. Resolved per-call (not import time) so tests that
        redirect ``$HOME`` see the updated value.

        Args:
            environ: Environment variable mapping to read ``XDG_CONFIG_HOME``
                from.

        Returns:
            The path to ``paddock/config.toml`` under the config base directory.
            It may not exist on disk.
        """
        xdg_config_home = Path(environ.get("XDG_CONFIG_HOME", ""))
        base = (
            xdg_config_home
            if xdg_config_home.is_absolute()
            else Path.home() / ".config"
        )
        return base / "paddock" / "config.toml"
