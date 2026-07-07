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

# Sources whose load output is allowlist-gated. Trusted sources skip this.
_GATED_SOURCES = frozenset({"project_toml", "env", "cli"})


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
        context = ConfigContext(
            parsed=parsed,
            environ=dict(environ),
            workdir=workdir,
            user_config_path=(
                self._user_path_override or ConfigContext.default_user_config_path()
            ),
        )

        # Phase 1: Load every source via registry iteration (WEIGHT-ascending).
        results: dict[str, LoadResult] = {
            str(key): cls().load(context) for key, cls in source_registry.items()
        }

        # Phase 2: Build allowlist + project_dir_readonly from source meta.
        allowlist, project_dir_readonly = self._extract_meta(results)

        # Phase 3a: Aggregate validation errors generically.
        bad: list[tuple[str, f.FilterRunner]] = []
        for key, result in results.items():
            if result.instance.is_valid():
                continue
            if key in _GATED_SOURCES and not allowlist.is_enabled(key):
                logger.warning(
                    "%s source had errors but is disabled by [config.allowlist] — ignored",
                    key,
                )
                continue
            bad.append((key, result.instance))
        if bad:
            raise self._error_group(bad)

        # Phase 3b: Warn-if-ignored generically for any gated source that
        # contributed content while disabled.
        for key in _GATED_SOURCES:
            if allowlist.is_enabled(key):
                continue
            instance = results[key].instance
            if instance.is_valid() and instance.cleaned_data:
                logger.warning(
                    "%s contributed config but %s is not in [config.allowlist] — ignored",
                    key,
                    key,
                )

        # Phase 3c: Sanitise — allowlist-gated sources are filtered; everything
        # else passes through unchanged. Task 3 makes this fully generic.
        sanitised: dict[str, dict] = {}
        for key, result in results.items():
            data = (
                dict(result.instance.cleaned_data) if result.instance.is_valid() else {}
            )
            sanitised[key] = (
                allowlist.filter(data, key) if key in _GATED_SOURCES else data
            )

        # Phase 4: Merge in registry (= WEIGHT) order, then validate the final dict.
        merged: dict = {}
        for key in sanitised:
            merged = self._deep_merge(merged, sanitised[key])
        merged = self._apply_defaults(merged)

        final = f.FilterRunner(standard_config_schema(merged=True), merged)
        if not final.is_valid():
            raise self._error_group([("final", final)])

        return ResolvedConfig(
            config=final.cleaned_data,
            project_toml_enabled=allowlist.is_enabled("project_toml"),
            project_dir_readonly=project_dir_readonly,
        )

    # ------------------------------------------------------------------

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

        return Allowlist(allowlist_raw), bool(readonly)

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
