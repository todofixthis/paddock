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
    the loader's sanitise phase (Task 8), so even a disabled source can still
    be inspected for warning purposes.
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
        schema = standard_config_schema(merged=False)
        path = context.workdir / _CONFIG_NAME
        if not path.exists():
            return LoadResult(f.FilterRunner(schema, {}), {})

        chain = f.TomlDecode | schema
        return LoadResult(f.FilterRunner(chain, path.read_text(encoding="utf-8")), {})
