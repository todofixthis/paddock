from pathlib import Path

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.project_dir import PROJECT_DIR_NAME
from paddock.config.schema import standard_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult

_CONFIG_NAME = Path(PROJECT_DIR_NAME) / "config.toml"


class ProjectTomlSource(ConfigSource):
    """Loads ``<workdir>/.paddock/config.toml``.

    Loading is unconditional — gating by the allowlist happens generically in
    the loader's sanitise phase, so even a disabled source can still be
    inspected for warning purposes.
    """

    SOURCE_KEY = "project_toml"
    WEIGHT = 10
    ALLOWLIST_DEFAULT = False

    def load(self, context: ConfigContext) -> LoadResult:
        """Load config from ``<workdir>/.paddock/config.toml``.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``,
            with empty meta (project TOML carries no ``[config]`` section).
            Returns an empty valid instance when the file is absent.
        """
        # Relative paths belong to the project, not .paddock/ (ADR 012).
        schema = standard_config_schema(base_dir=context.workdir, merged=False)
        path = context.workdir / _CONFIG_NAME
        if not path.exists():
            return LoadResult(f.FilterRunner(schema, {}), {})

        text = path.read_text(encoding="utf-8")
        decoded = f.FilterRunner(f.TomlDecode, text)
        if not decoded.is_valid():
            return LoadResult(f.FilterRunner(f.TomlDecode | schema, text), {})

        data = dict(decoded.cleaned_data)
        discarded = self._discard_server_settings(data)
        return LoadResult(f.FilterRunner(schema, data), {}, discarded)

    def _discard_server_settings(self, data: dict) -> list[str]:
        """Remove every ``agents.<name>.server`` from decoded project config.

        A project file may never set a shared server's settings, whatever the
        allowlist grants, and must not be able to stop a run by getting them
        wrong, so they go before validation (ADR 019). Anything that is not
        the expected table is left for validation to report.

        Args:
            data: The decoded project file; ``agents`` is replaced by a copy
                without the server settings.

        Returns:
            The dotted path of each table removed.
        """
        agents = data.get("agents")
        if not isinstance(agents, dict):
            return []

        discarded: list[str] = []
        kept: dict = {}
        for name, settings in agents.items():
            if isinstance(settings, dict) and "server" in settings:
                settings = {k: v for k, v in settings.items() if k != "server"}
                discarded.append(f"agents.{name}.server")
            kept[name] = settings
        data["agents"] = kept
        return discarded
