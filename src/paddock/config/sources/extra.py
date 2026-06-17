from pathlib import Path

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.schema import standard_config_schema, user_config_schema
from paddock.config.sources.base import ConfigSource


class ExtraConfigSource(ConfigSource):
    """Loads an extra user-shaped TOML file via ``--config-file`` / ``PADDOCK_CONFIG_FILE``.

    CLI wins over env. The file has the same shape as the main user config
    (standard fields + ``[projects]`` + ``[config]``); only the standard global
    fields are surfaced here — ``[projects]`` and ``[config]`` in an extra
    config file are intentionally ignored.
    """

    SOURCE_KEY = "extra"
    WEIGHT = 40

    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Load config from the extra config file, if any.

        Returns:
            A :class:`filters.FilterRunner` over
            ``standard_config_schema(merged=False)``. Returns an empty valid
            runner when no path is configured or the file does not exist.
        """
        schema = standard_config_schema(merged=False)
        path = self._resolve_path(context)
        if path is None or not path.exists():
            return f.FilterRunner(schema, {})

        content = path.read_text(encoding="utf-8")
        full_runner = f.FilterRunner(user_config_schema, content)
        if not full_runner.is_valid():
            return full_runner

        cleaned = full_runner.cleaned_data
        stripped = {k: v for k, v in cleaned.items() if k not in {"projects", "config"}}
        return f.FilterRunner(schema, stripped)

    def _resolve_path(self, context: ConfigContext) -> Path | None:
        """Return the extra config path from parsed args or environ.

        CLI ``--config-file`` wins over ``PADDOCK_CONFIG_FILE``.
        """
        if context.parsed.config_file is not None:
            return Path(context.parsed.config_file).expanduser()
        env_path = context.environ.get("PADDOCK_CONFIG_FILE")
        if env_path:
            return Path(env_path).expanduser()
        return None
