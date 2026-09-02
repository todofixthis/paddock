from typing import Any, cast

from paddock.config.fields import CONFIG_FIELDS


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
        """Whether a source may contribute to the merged config at all.

        The trusted ``user`` source is always enabled, regardless of any
        rule. Any other source is enabled if its rule is ``True`` or a
        non-empty list of dotted paths; a key present in neither
        ``defaults`` nor the user-supplied ``raw`` rules is blocked
        (default-deny).

        Args:
            source_key: The canonical source identifier (e.g. ``"env"``).

        Returns:
            Whether the source may contribute any keys.
        """
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
        """Return the permitted config plus a report of what was dropped.

        Mirrors the ``user``-always-enabled behaviour of :meth:`is_enabled`:
        the trusted ``user`` source always passes its config through
        unfiltered, regardless of any rule.

        Args:
            config: The fully-validated ``cleaned_data`` dict from a source
                runner.
            source_key: The canonical source identifier (e.g. ``"env"``).

        Returns:
            A ``(kept, dropped)`` tuple: ``kept`` is a filtered copy of
            ``config`` containing only the allowed keys, and ``dropped`` is
            the sorted list of dotted leaf paths removed, for a single
            consolidated warning.
        """
        if source_key == "user":
            return dict(config), []
        if not self.is_enabled(source_key):
            return {}, sorted(self._leaf_paths(config))
        value = self._rules.get(source_key, False)
        if value is True:
            return dict(config), []
        kept = self._project(config, cast(list[str], value))
        dropped = sorted(set(self._leaf_paths(config)) - set(self._leaf_paths(kept)))
        return kept, dropped

    def _leaf_paths(self, config: dict, prefix: str = "") -> list[str]:
        """List every leaf of ``config`` as a dotted path.

        Descends only where :data:`CONFIG_FIELDS` declares children, so a
        dropped sibling is named in full (``build.dockerfile``) while a
        free-form map (``build.args``, ``volumes``) stays one path — its
        keys are user data, not schema fields, and must never reach a
        warning. ``CONFIG_FIELDS`` keys are top-level only, so any nested
        path is a leaf; an empty table is likewise a leaf.

        Args:
            config: Dict to walk.
            prefix: Dotted path of ``config`` itself, ``"."``-terminated.

        Returns:
            The dotted paths of every leaf, in traversal order.
        """
        paths: list[str] = []
        for key, value in config.items():
            path = f"{prefix}{key}"
            if isinstance(value, dict) and value and CONFIG_FIELDS.get(path):
                paths.extend(self._leaf_paths(value, f"{path}."))
            else:
                paths.append(path)
        return paths

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
