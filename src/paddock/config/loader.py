import logging
from dataclasses import dataclass
from pathlib import Path

import filters as f

from paddock.cli import ParsedArgs
from paddock.config.allowlist import Allowlist
from paddock.config.context import ConfigContext
from paddock.config.errors import ConfigError
from paddock.config.schema import standard_config_schema
from paddock.config.sources import source_registry
from paddock.config.sources.base import LoadResult

logger = logging.getLogger("paddock")


@dataclass
class ResolvedConfig:
    """The result of a full config resolution."""

    config: dict
    project_toml_enabled: bool
    project_dir_readonly: bool


class ConfigLoader:
    """Orchestrates loading, validation, sanitisation, and reduction of config.

    The merge order, source list, and per-source loaders all come from
    :data:`source_registry`. To add a new source, define a ``ConfigSource``
    subclass with a ``SOURCE_KEY`` and ``WEIGHT``; ``AutoRegister`` does the rest.
    """

    def __init__(self, user_config_path: Path | None = None) -> None:
        """Initialises the loader with an optional user config path override.

        Args:
            user_config_path: If provided, overrides the default user config
                path (``~/.config/paddock/config.toml``). Useful for testing.
        """
        self._user_path_override = user_config_path

    def resolve(
        self,
        parsed: ParsedArgs,
        workdir: Path,
        environ: dict[str, str],
    ) -> ResolvedConfig:
        """Load config from all sources, merge, apply defaults, and validate.

        Args:
            parsed: Parsed CLI arguments object.
            workdir: The project working directory.
            environ: Environment variable mapping (e.g. ``dict(os.environ)``).

        Returns:
            A :class:`ResolvedConfig` containing the validated merged config
            and metadata derived from trusted sources.

        Raises:
            ExceptionGroup: If any enabled source fails validation, or if the
                final merged config fails validation.
        """
        context = self._build_context(parsed, workdir, environ)
        results = self._load_sources(context)
        allowlist, readonly = self._extract_meta(results)
        self._validate(results, allowlist)
        self._warn_ignored(results, allowlist)
        merged = self._merge(self._sanitise(results, allowlist))

        final = f.FilterRunner(standard_config_schema(merged=True), merged)
        if not final.is_valid():
            raise self._error_group([("final", final)])

        return ResolvedConfig(
            config=final.cleaned_data,
            project_toml_enabled=allowlist.is_enabled("project_toml"),
            project_dir_readonly=readonly,
        )

    # ------------------------------------------------------------------

    def _build_context(
        self,
        parsed: ParsedArgs,
        workdir: Path,
        environ: dict[str, str],
    ) -> ConfigContext:
        """Assemble the :class:`ConfigContext` shared by every source.

        Args:
            parsed: Parsed CLI arguments object.
            workdir: The project working directory.
            environ: Environment variable mapping (e.g. ``dict(os.environ)``).

        Returns:
            A :class:`ConfigContext` ready to pass to each source's ``load``.
        """
        return ConfigContext(
            parsed=parsed,
            environ=dict(environ),
            workdir=workdir,
            user_config_path=(
                self._user_path_override or ConfigContext.default_user_config_path()
            ),
        )

    def _load_sources(self, context: ConfigContext) -> dict[str, LoadResult]:
        """Load every registered source (WEIGHT-ascending) against ``context``.

        # class_registry instantiates on subscription. Iterating keys +
        # subscripting (rather than .items()/cls()) lets a future
        # ClassRegistryInstanceCache slot in transparently. The str()
        # coercion drops once todofixthis/class-registry#100 ships a typed
        # key.

        Args:
            context: The shared config context to load each source with.

        Returns:
            The loaded results keyed by source key.
        """
        return {str(key): source_registry[key].load(context) for key in source_registry}

    def _validate(
        self,
        results: dict[str, LoadResult],
        allowlist: Allowlist,
    ) -> None:
        """Raise on validation errors from any allowlisted source.

        Errors from sources disabled by the allowlist are logged and
        otherwise ignored.

        Args:
            results: The loaded results keyed by source key.
            allowlist: The resolved allowlist controlling which sources'
                errors are fatal.

        Raises:
            ExceptionGroup: If any allowlisted source failed validation.
        """
        bad: list[tuple[str, f.FilterRunner]] = []
        for key, result in results.items():
            if result.instance.is_valid():
                continue
            if not allowlist.is_enabled(key):
                logger.warning(
                    "%s source had errors but is disabled by [config.allowlist] — ignored",
                    key,
                )
                continue
            bad.append((key, result.instance))
        if bad:
            raise self._error_group(bad)

    def _warn_ignored(
        self,
        results: dict[str, LoadResult],
        allowlist: Allowlist,
    ) -> None:
        """Warn about disabled sources that would otherwise contribute config.

        Args:
            results: The loaded results keyed by source key.
            allowlist: The resolved allowlist controlling which sources are
                enabled.
        """
        for key, result in results.items():
            if allowlist.is_enabled(key):
                continue
            instance = result.instance
            if instance.is_valid() and instance.cleaned_data:
                logger.warning(
                    "%s contributed config but %s is not in [config.allowlist] — ignored",
                    key,
                    key,
                )

    def _sanitise(
        self,
        results: dict[str, LoadResult],
        allowlist: Allowlist,
    ) -> dict[str, dict]:
        """Filter every source's cleaned data through the allowlist.

        Consolidates the dropped keys into a single warning per source.

        Args:
            results: The loaded results keyed by source key.
            allowlist: The resolved allowlist controlling which keys survive.

        Returns:
            The allowlisted config data keyed by source key.
        """
        sanitised: dict[str, dict] = {}
        for key, result in results.items():
            # dict() coercion drops once todofixthis/filters#98 types
            # cleaned_data.
            data = (
                dict(result.instance.cleaned_data) if result.instance.is_valid() else {}
            )
            kept, dropped = allowlist.filter_with_report(data, key)
            sanitised[key] = kept
            if dropped:
                logger.warning(
                    "%s: dropped non-allowlisted keys %s — add them to "
                    "[config.allowlist].%s to keep them",
                    key,
                    ", ".join(dropped),
                    key,
                )
        return sanitised

    def _merge(self, sanitised: dict[str, dict]) -> dict:
        """Deep-merge sanitised source data in registry (= WEIGHT) order.

        Args:
            sanitised: The allowlisted config data keyed by source key.

        Returns:
            The merged config dict with defaults applied.
        """
        merged: dict = {}
        for key in sanitised:
            merged = self._deep_merge(merged, sanitised[key])
        return self._apply_defaults(merged)

    def _extract_meta(self, results: dict[str, LoadResult]) -> tuple[Allowlist, bool]:
        """Build the Allowlist + project_dir_readonly from source-provided meta.

        Args:
            results: The loaded results keyed by source key.

        Returns:
            A tuple of ``(Allowlist, project_dir_readonly)``.
        """
        user_meta = results["user"].meta
        po_meta = results["project_overrides"].meta

        def _explicit(allowlist: dict | None) -> dict:
            # Keep only keys the user actually set; drop the None placeholders
            # the mapper injects for unset keys so class defaults survive the
            # overlay.
            return {k: v for k, v in (allowlist or {}).items() if v is not None}

        allowlist_raw = {
            **_explicit(user_meta.get("allowlist")),
            **_explicit(po_meta.get("allowlist")),
        }

        readonly = po_meta.get("project_dir_readonly")
        if readonly is None:
            readonly = user_meta.get("project_dir_readonly")
        if readonly is None:
            readonly = True

        defaults = {
            str(key): source_registry[key].ALLOWLIST_DEFAULT for key in source_registry
        }
        return Allowlist(defaults, allowlist_raw), bool(readonly)

    def _error_group(self, bad: list[tuple[str, f.FilterRunner]]) -> ExceptionGroup:
        """Build an ``ExceptionGroup`` from a list of invalid runners.

        Args:
            bad: List of ``(source_key, runner)`` pairs where the runner is
                not valid.

        Returns:
            An ``ExceptionGroup`` wrapping one :class:`ConfigError` per
            validation message.
        """
        errors: list[ConfigError] = []
        for source_key, runner in bad:
            for key, messages in runner.errors.items():
                for msg in messages:
                    errors.append(ConfigError(f"[{source_key}:{key}] {msg['message']}"))
        return ExceptionGroup("config validation failed", errors)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge ``override`` into ``base``.

        Args:
            base: The base dict to merge into.
            override: The dict whose values take precedence.

        Returns:
            A new merged dict.
        """
        result = dict(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _apply_defaults(self, config: dict) -> dict:
        """Apply default values for omitted config keys.

        Mutates and returns ``config``.

        Args:
            config: The plain config dict to fill.

        Returns:
            The same dict with defaults applied.
        """
        config.setdefault("agent", "claude")
        config.setdefault("volumes", {})
        if isinstance(config.get("build"), dict):
            config["build"].setdefault("args", {})
            config["build"].setdefault("context", None)
            config["build"].setdefault("policy", "if-missing")
        return config
