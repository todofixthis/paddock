from paddock.config.sources.base import ConfigSource, source_registry

# Uncomment each import as the corresponding module is added (Tasks 3-5):
# from paddock.config.sources.cli import CliConfigSource
# from paddock.config.sources.env import EnvConfigSource
# from paddock.config.sources.extra import ExtraConfigSource
# from paddock.config.sources.project_overrides import ProjectOverridesSource
# from paddock.config.sources.project_toml import ProjectTomlSource
# from paddock.config.sources.user import UserConfigSource

__all__ = [
    "ConfigSource",
    "source_registry",
]
