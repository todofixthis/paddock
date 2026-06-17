import filters as f

from paddock.config.context import ConfigContext
from paddock.config.extract import ExtractProject
from paddock.config.schema import config_meta_schema, standard_config_schema
from paddock.config.sources.base import ConfigSource


class ProjectOverridesSource(ConfigSource):
    """Reads ``[projects."<context.project_key>"]`` out of the user config file."""

    SOURCE_KEY = "project_overrides"
    WEIGHT = 30

    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Load per-project overrides from the user config file.

        Returns:
            A :class:`filters.FilterRunner` over
            ``standard_config_schema(extra_keys={"config": ...}, merged=False)``.
            Returns an empty valid runner when the file is missing or the
            project key is not present.
        """
        path = context.user_config_path
        schema = standard_config_schema(
            extra_keys={"config": config_meta_schema}, merged=False
        )
        if not path.exists():
            return f.FilterRunner(schema, {})

        chain = f.TomlDecode | ExtractProject(project=context.project_key) | schema
        return f.FilterRunner(chain, path.read_text(encoding="utf-8"))
