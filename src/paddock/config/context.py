import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from paddock.cli import ParsedArgs

logger = logging.getLogger("paddock")


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

        Where ``XDG_CONFIG_HOME`` names somewhere other than ``~/.config``,
        a config left at ``~/.config/paddock/config.toml`` is still honoured
        when the XDG one is missing, with a deprecation warning, and reported
        as ignored when both exist. The fallback goes in paddock 2.0; see
        ``docs/future/v2-deprecations.md``.

        Args:
            environ: Environment variable mapping to read ``XDG_CONFIG_HOME``
                from.

        Returns:
            The path to the user config file. It may not exist on disk.
        """
        legacy = Path.home() / ".config" / "paddock" / "config.toml"
        xdg_config_home = Path(environ.get("XDG_CONFIG_HOME", ""))
        if not xdg_config_home.is_absolute():
            return legacy

        xdg = xdg_config_home / "paddock" / "config.toml"
        if not legacy.exists():
            return xdg

        if not xdg.exists():
            logger.warning(
                "Reading user config from %s because XDG_CONFIG_HOME is set and "
                "%s does not exist. This fallback is deprecated and will be "
                "removed in paddock 2.0; move the file to %s.",
                legacy,
                xdg,
                xdg,
            )
            return legacy

        # XDG_CONFIG_HOME may reach ~/.config itself, directly or through a
        # symlink, in which case the two paths name one file.
        if xdg.samefile(legacy):
            return xdg

        logger.warning(
            "Ignoring %s because XDG_CONFIG_HOME is set; reading user config "
            "from %s. Remove %s, merging anything it still needs into the XDG "
            "file.",
            legacy,
            xdg,
            legacy,
        )
        return xdg
