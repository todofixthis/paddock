from typing import Any, ClassVar

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.filters import Agent, Filepath
from paddock.config.schema import BUILD_POLICIES, standard_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult

# Validates the raw PADDOCK_* shape. Lifted from the old top-level
# ``_env_schema`` in the loader so that env validation is fully owned here.
_env_schema = f.FilterMapper(
    {
        "PADDOCK_AGENT": Agent,
        "PADDOCK_BUILD_CONTEXT": f.Unicode | f.NotEmpty | Filepath(is_dir=True),
        "PADDOCK_BUILD_DOCKERFILE": f.Unicode | f.NotEmpty | Filepath(is_dir=False),
        "PADDOCK_BUILD_POLICY": f.Choice(BUILD_POLICIES),
        "PADDOCK_IMAGE": f.Unicode | f.NotEmpty,
        "PADDOCK_NETWORK": f.Unicode,
    },
    allow_extra_keys=True,
    allow_missing_keys=True,
)


class EnvConfigSource(ConfigSource):
    """Reads config from ``PADDOCK_*`` environment variables.

    Owns the entire env-vars pipeline:

    1. Filter ``context.environ`` down to the ``PADDOCK_*`` subset (minus the
       loader-handled keys).
    2. Validate values via the private ``_env_schema``.
    3. Transform the validated PADDOCK_*-keyed dict into the standard config
       shape (``PADDOCK_BUILD_DOCKERFILE`` → ``build.dockerfile``).
    4. Run the result through ``standard_config_schema(merged=False)`` so the
       returned runner is shape-compatible with every other source.
    """

    SOURCE_KEY = "env"
    WEIGHT = 50
    PREFIX: ClassVar[str] = "PADDOCK_"

    # PADDOCK_* keys deliberately excluded from the env-to-config mapping:
    #   * PADDOCK_CONFIG_FILE — consumed by ``ExtraConfigSource`` to locate an
    #     extra config file; it is not itself a config value.
    #   * PADDOCK_BUILD_ARGS — build args cannot be expressed as a single scalar
    #     env var, so there is no env mapping; they arrive via CLI ``--build-arg``
    #     or a config file's ``build.args``.
    _LOADER_KEYS = frozenset({"PADDOCK_CONFIG_FILE", "PADDOCK_BUILD_ARGS"})

    def load(self, context: ConfigContext) -> LoadResult:
        """Load config from PADDOCK_* environment variables.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``,
            with empty meta (env carries no ``[config]`` section). Returns an
            empty valid instance when no relevant env vars are present.
            Returns an invalid instance when env-shape validation fails.
        """
        raw_env = {
            k: v
            for k, v in context.environ.items()
            if k.startswith(self.PREFIX) and k not in self._LOADER_KEYS
        }

        env_runner = f.FilterRunner(_env_schema, raw_env)
        if not env_runner.is_valid():
            return LoadResult(env_runner, {})

        cleaned_env = {
            k: v
            for k, v in env_runner.cleaned_data.items()
            if v is not None and v != ""
        }

        shaped: dict[str, Any] = {}
        for key, value in cleaned_env.items():
            parts = key[len(self.PREFIX) :].lower().split("_")
            self._deep_set(shaped, parts, value)

        return LoadResult(
            f.FilterRunner(standard_config_schema(merged=False), shaped), {}
        )

    def _deep_set(self, node: dict, parts: list[str], value: Any) -> None:
        """Deep-set ``value`` in ``node`` at the path described by ``parts``.

        Descends into nested dicts, creating sub-dicts as needed. Skips the
        assignment if the target slot already holds a dict (guard against
        partial-key collisions).
        """
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        if isinstance(node.get(parts[-1]), dict):
            return
        node[parts[-1]] = value
