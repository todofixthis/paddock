import filters as f

from paddock.config.context import ConfigContext
from paddock.config.extract import ExtractProject
from paddock.config.schema import project_entry_schema, standard_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult


class ProjectOverridesSource(ConfigSource):
    """Reads ``[projects."<context.project_key>"]`` out of the user config file."""

    SOURCE_KEY = "project_overrides"
    WEIGHT = 30
    ALLOWLIST_DEFAULT = True

    def load(self, context: ConfigContext) -> LoadResult:
        """Load per-project overrides from the user config file.

        Returns:
            A :class:`LoadResult` whose ``instance`` conforms to
            ``standard_config_schema(merged=False)`` and whose ``meta`` is the
            project entry's validated ``[config]`` section. Returns an empty
            valid instance and empty meta when the file is missing or the
            project key is not present.
        """
        schema = standard_config_schema(merged=False)
        path = context.user_config_path
        if not path.exists():
            return LoadResult(f.FilterRunner(schema, {}), {})

        project = context.project_key
        chain = (
            f.TomlDecode
            | ExtractProject(project=project)
            | project_entry_schema(project)
        )
        full = f.FilterRunner(chain, path.read_text(encoding="utf-8"))
        if not full.is_valid():
            return LoadResult(full, {})

        cleaned = full.cleaned_data
        instance = {k: v for k, v in cleaned.items() if k != "config"}
        return LoadResult(f.FilterRunner(schema, instance), cleaned.get("config") or {})
