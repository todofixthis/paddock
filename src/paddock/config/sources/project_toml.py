from pathlib import Path

import filters as f

from paddock.config.allowlist import Allowlist
from paddock.config.context import ConfigContext
from paddock.config.project_dir import PROJECT_DIR_NAME
from paddock.config.schema import standard_config_schema
from paddock.config.sources.base import ConfigSource

_CONFIG_NAME = Path(PROJECT_DIR_NAME) / "config.toml"


class ProjectTomlSource(ConfigSource):
    """Loads ``<workdir>/.paddock/config.toml``.

    Loading is unconditional — gating by the allowlist happens generically in
    the loader's sanitise phase (Task 8), so even a disabled source can still
    be inspected for warning purposes.
    """

    SOURCE_KEY = "project_toml"
    WEIGHT = 10

    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Load config from ``<workdir>/.paddock/config.toml``.

        Returns:
            A :class:`filters.FilterRunner` over
            ``standard_config_schema(merged=False)``. Returns an empty valid
            runner when the file is absent.
        """
        schema = standard_config_schema(merged=False)
        path = context.workdir / _CONFIG_NAME
        if not path.exists():
            return f.FilterRunner(schema, {})

        chain = f.TomlDecode | schema
        return f.FilterRunner(chain, path.read_text(encoding="utf-8"))

    def sanitise(
        self, runner: f.FilterRunner, allowlist: Allowlist | None
    ) -> f.FilterRunner:
        """Drop keys not permitted by the allowlist for this source.

        No-op when ``allowlist`` is ``None``.
        """
        if allowlist is None or not runner.is_valid():
            return runner
        filtered = allowlist.filter(runner.cleaned_data, self.SOURCE_KEY)
        return f.FilterRunner(standard_config_schema(merged=False), filtered)
