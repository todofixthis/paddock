import logging
from dataclasses import dataclass
from pathlib import Path

import filters as f

from class_registry.base import BaseRegistry

from paddock.agents import agent_registry
from paddock.cli import ParsedArgs
from paddock.config.agent_choice import UNNAMED_SERVER
from paddock.config.allowlist import Allowlist
from paddock.config.context import ConfigContext
from paddock.config.errors import ConfigError
from paddock.config.schema import standard_config_schema
from paddock.config.sources import source_registry
from paddock.config.sources.base import LoadResult

logger = logging.getLogger("paddock")


@dataclass
class ResolvedConfig:
    """The result of a full config resolution.

    Attributes:
        config: The validated merged config. Its ``agent`` is a table with
            both halves resolved: ``client`` a name or ``False``, ``server``
            a name or ``False``.
        agent_key: The chosen client's registry key; ``"false"`` for the
            no-agent shell, whose client half is the boolean ``False``.
        server_key: The chosen server's registry key, or ``None`` for none.
        extra_args: The chosen agent's configured ``extra_args`` (ADR 017);
            empty when it has none.
        project_toml_enabled: Whether the allowlist enables the project file.
        project_dir_readonly: Whether ``.paddock`` mounts read-only.
    """

    config: dict
    agent_key: str
    server_key: str | None
    extra_args: list[str]
    project_toml_enabled: bool
    project_dir_readonly: bool


class ConfigLoader:
    """Orchestrates loading, validation, sanitisation, and reduction of config.

    The merge order, source list, and per-source loaders all come from
    :data:`source_registry`. To add a new source, define a ``ConfigSource``
    subclass with a ``SOURCE_KEY`` and ``WEIGHT``; ``AutoRegister`` does the rest.
    """

    def __init__(
        self,
        user_config_path: Path | None = None,
        *,
        agents: BaseRegistry = agent_registry,
    ) -> None:
        """Initialises the loader with an optional user config path override.

        Args:
            user_config_path: If provided, overrides the default user config
                path (``$XDG_CONFIG_HOME/paddock/config.toml``, defaulting to
                ``~/.config/paddock/config.toml``). Useful for testing.
            agents: The registry of clients, consulted for a client's default
                server and for which ``agents`` entries are installed.
        """
        self._user_path_override = user_config_path
        self._agents = agents

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
        merged = self._merge(self._sanitise(results, allowlist))

        # Every source has already made its paths absolute, so the base is moot.
        final = f.FilterRunner(
            standard_config_schema(base_dir=workdir, merged=True), merged
        )
        if not final.is_valid():
            raise self._error_group([("final", final)])

        config = dict(final.cleaned_data)
        agent_key = self._agent_key(config["agent"]["client"])
        server_key = self._resolve_server(config["agent"], agent_key)
        self._warn_unknown_agent_settings(config)

        return ResolvedConfig(
            config=config,
            agent_key=agent_key,
            server_key=server_key,
            extra_args=self._extra_args(config, agent_key),
            project_toml_enabled=allowlist.is_enabled("project_toml"),
            project_dir_readonly=readonly,
        )

    def _agent_key(self, configured: str | bool) -> str:
        """Return the registry key for the merged config's ``agent`` value.

        Args:
            configured: An agent key, or ``False`` for the no-agent shell.

        Returns:
            The key the agent is registered under; ``"false"`` for the shell.
        """
        return "false" if configured is False else str(configured)

    def _resolve_server(self, agent: dict, agent_key: str) -> str | None:
        """Resolve the server half of the merged ``agent``, in place.

        An unnamed server becomes the merged client's ``DEFAULT_SERVER``
        (ADR 018). A client that is not installed has no default; the entry
        point reports it.

        Args:
            agent: The merged ``agent`` table; its ``server`` is replaced by
                the resolved name, or ``False`` for none.
            agent_key: The chosen client's registry key.

        Returns:
            The server's registry key, or ``None`` for no server.
        """
        server = agent["server"]
        if server == UNNAMED_SERVER:
            server = False
            if agent_key in self._agents:
                server = self._agents.get_class(agent_key).DEFAULT_SERVER or False
        agent["server"] = server
        return server or None

    def _extra_args(self, config: dict, agent_key: str) -> list[str]:
        """Return the configured ``extra_args`` for one agent (ADR 017).

        Args:
            config: The merged config.
            agent_key: The chosen agent's registry key.

        Returns:
            The arguments to place after the agent's command and before the
            command line's own; empty when the agent has none configured.
        """
        return config.get("agents", {}).get(agent_key, {}).get("extra_args", [])

    def _warn_unknown_agent_settings(self, config: dict) -> None:
        """Warn about ``agents`` entries that name no installed agent.

        A warning, not an error, so a config shared between machines still
        loads where a plugin's agent is missing (ADR 017).

        Args:
            config: The merged config.
        """
        for name in sorted(config.get("agents", {})):
            if name not in self._agents:
                logger.warning(
                    '[agents.%s] No agent named "%s" is installed, so its '
                    "settings are ignored; installed agents: %s",
                    name,
                    name,
                    ", ".join(sorted(str(key) for key in self._agents)),
                )

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
                self._user_path_override
                or ConfigContext.default_user_config_path(environ)
            ),
        )

    def _load_sources(self, context: ConfigContext) -> dict[str, LoadResult]:
        """Load every registered source (WEIGHT-ascending) against ``context``.

        Args:
            context: The shared config context to load each source with.

        Returns:
            The loaded results keyed by source key.
        """
        # class_registry instantiates on subscription. Iterating keys +
        # subscripting (rather than .items()/cls()) lets a future
        # ClassRegistryInstanceCache slot in transparently. The str()
        # coercion drops once todofixthis/class-registry#100 ships a typed
        # key.
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
                # A failure at the root of a source's chain (e.g. undecodable
                # TOML) has no key, so the label is the source alone.
                label = f"{source_key}:{key}" if key else source_key
                for msg in messages:
                    errors.append(ConfigError(f"[{label}] {msg['message']}"))
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
        agent = config.setdefault("agent", {})
        agent.setdefault("client", "claude")
        agent.setdefault("server", UNNAMED_SERVER)
        config.setdefault("volumes", {})
        if isinstance(config.get("build"), dict):
            config["build"].setdefault("args", {})
            config["build"].setdefault("context", None)
            config["build"].setdefault("policy", "if-missing")
        return config
