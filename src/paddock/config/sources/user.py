import filters as f

from paddock.config.context import ConfigContext
from paddock.config.schema import standard_config_schema, user_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult


class UserConfigSource(ConfigSource):
    """Loads the user-level config from ``context.user_config_path``.

    Returns a :class:`LoadResult` whose ``instance.cleaned_data`` is the
    standard config object — global ``image``/``agent``/``build``/``network``/
    ``volumes`` only — and whose ``meta`` is the validated ``[config]``
    section. The ``projects`` section, while valid in the file, is stripped
    from ``instance``; it is consumed by ``ProjectOverridesSource``.
    """

    SOURCE_KEY = "user"
    WEIGHT = 20
    ALLOWLIST_DEFAULT = True

    def load(self, context: ConfigContext) -> LoadResult:
        """Load user config from ``context.user_config_path``.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``.
            If the file does not exist, ``instance`` has ``cleaned_data == {}``
            and ``meta == {}``. If the TOML is invalid, ``instance`` is not
            valid and ``meta == {}``.
        """
        schema = standard_config_schema(merged=False)
        path = context.user_config_path
        if not path.exists():
            return LoadResult(f.FilterRunner(schema, {}), {})

        full = f.FilterRunner(user_config_schema, path.read_text(encoding="utf-8"))
        if not full.is_valid():
            return LoadResult(full, {})

        cleaned = full.cleaned_data
        instance = {
            k: v for k, v in cleaned.items() if k not in self._META_SECTION_KEYS
        }
        return LoadResult(f.FilterRunner(schema, instance), cleaned.get("config") or {})
