from typing import Any

_DEFAULTS: dict[str, bool | list[str]] = {
    "cli": True,
    "env": True,
    "project_toml": False,
}


class Allowlist:
    """Applies ``[config.allowlist]`` rules to a source's validated config.

    A rule may be ``True`` (permit everything), ``False`` or ``[]`` (block
    everything), or a list of dotted paths (e.g. ``["image", "build.dockerfile"]``)
    naming the allowed keys.

    Sources without an explicit rule default per :data:`_DEFAULTS`. Trusted
    sources (``user``, ``project_overrides``, ``extra``) are not allowlist-gated
    and are not represented here — callers query only the three untrusted
    source keys.
    """

    def __init__(self, raw: dict[str, Any]) -> None:
        """Initialises the allowlist from a raw rules dict.

        Args:
            raw: Mapping of source keys to their rules. Missing keys fall back
                to :data:`_DEFAULTS`.
        """
        self._rules: dict[str, bool | list[str]] = {**_DEFAULTS, **(raw or {})}

    def is_enabled(self, source_key: str) -> bool:
        """Return whether a source is permitted to contribute any config.

        Args:
            source_key: The canonical source identifier (e.g. ``"env"``).

        Returns:
            ``True`` if the source is enabled; ``False`` otherwise.
        """
        value = self._rules.get(source_key, True)
        if isinstance(value, bool):
            return value
        return len(value) > 0

    def filter(self, config: dict, source_key: str) -> dict:
        """Return only the config keys permitted for a given source.

        Args:
            config: The fully-validated ``cleaned_data`` dict from a source runner.
            source_key: The canonical source identifier (e.g. ``"env"``).

        Returns:
            A filtered copy of ``config`` containing only the allowed keys.
            Returns ``{}`` if the source is disabled.
        """
        if not self.is_enabled(source_key):
            return {}
        value = self._rules.get(source_key, True)
        if value is True:
            return config
        return self._project(config, value)  # type: ignore[arg-type]

    def _project(self, config: dict, paths: list[str]) -> dict:
        """Build a new dict from ``config`` containing only the given dotted paths.

        Args:
            config: Source dict to project from.
            paths: List of dotted-path strings (e.g. ``["image", "build.dockerfile"]``).

        Returns:
            A new dict containing only the specified paths.
        """
        out: dict = {}
        for path in paths:
            self._copy_path(config, out, path.split("."))
        return out

    def _copy_path(self, src: dict, dst: dict, parts: list[str]) -> None:
        """Copy a single dotted path from ``src`` into ``dst``.

        Descends into nested dicts, creating sub-dicts in ``dst`` as needed.
        Silently skips if the path does not exist in ``src`` or a non-dict
        is encountered at an intermediate segment.

        Args:
            src: Source dict to read from.
            dst: Destination dict to write into.
            parts: Path segments from a dotted path split on ``"."``.
        """
        if not parts:
            return
        head, *rest = parts
        if head not in src:
            return
        if not rest:
            dst[head] = src[head]
            return
        if not isinstance(src[head], dict):
            return
        child = dst.setdefault(head, {})
        self._copy_path(src[head], child, rest)
