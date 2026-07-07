from typing import Any, cast


class Allowlist:
    """Applies ``[config.allowlist]`` rules to a source's validated config.

    A rule may be ``True`` (permit everything), ``False`` or ``[]`` (block
    everything), or a list of dotted paths (e.g. ``["image", "build.dockerfile"]``)
    naming the allowed keys.

    Sources without an explicit rule default per the ``defaults`` mapping
    passed to the constructor — the loader builds this from each source
    class's ``ALLOWLIST_DEFAULT``. A key present in neither ``defaults`` nor
    the user-supplied ``raw`` rules is default-denied. The trusted ``user``
    source is always enabled regardless of any rule.
    """

    def __init__(
        self, defaults: dict[str, bool | list[str]], raw: dict[str, Any]
    ) -> None:
        """Initialises the allowlist from class defaults overlaid by user rules.

        Args:
            defaults: Mapping of source keys to their class-declared
                ``ALLOWLIST_DEFAULT``.
            raw: Mapping of source keys to user-supplied rules. Present keys
                override the matching entry in ``defaults``.
        """
        self._rules: dict[str, bool | list[str]] = {**defaults, **(raw or {})}

    def is_enabled(self, source_key: str) -> bool:
        """Whether a source may contribute. ``user`` is always enabled; an
        unknown key is blocked (default-deny)."""
        if source_key == "user":
            return True
        value = self._rules.get(source_key, False)
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
        return self.filter_with_report(config, source_key)[0]

    def filter_with_report(
        self, config: dict, source_key: str
    ) -> tuple[dict, list[str]]:
        """Return (kept, dropped) — the permitted config plus the sorted list of
        dropped top-level keys, for a single consolidated warning."""
        if not self.is_enabled(source_key):
            return {}, sorted(config)
        value = self._rules.get(source_key, True if source_key == "user" else False)
        if value is True:
            return dict(config), []
        kept = self._project(config, cast(list[str], value))
        dropped = sorted(set(config) - set(kept))
        return kept, dropped

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
