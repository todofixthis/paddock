from typing import Any, ClassVar

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.filters import Agent, Filepath, NoEnvForm
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

    1. Filter ``context.environ`` down to the ``PADDOCK_*`` subset.
    2. Reject names that target a field with no env form (``_NO_ENV_FORM``),
       then validate values via the private ``_env_schema``.
    3. Transform the validated PADDOCK_*-keyed dict into the standard config
       shape (``PADDOCK_BUILD_DOCKERFILE`` → ``build.dockerfile``).
    4. Run the result through ``standard_config_schema(merged=False)`` so the
       returned runner is shape-compatible with every other source.
    """

    SOURCE_KEY = "env"
    WEIGHT = 50
    ALLOWLIST_DEFAULT = True
    PREFIX: ClassVar[str] = "PADDOCK_"

    # Free-form maps keyed by user data (Dockerfile ARG names, host paths).
    # An env var name can't carry such a key faithfully — ``_`` splits it into
    # nested keys and its case is lost — so these names, bare or with a
    # ``_<NAME>`` suffix, are rejected rather than mapped. Values are
    # ``(field, flag)`` for the error message.
    _NO_ENV_FORM: ClassVar[dict[str, tuple[str, str]]] = {
        "PADDOCK_BUILD_ARGS": ("build.args", "--build-args-KEY=VALUE"),
        "PADDOCK_VOLUMES": ("volumes", "--volume"),
    }

    def load(self, context: ConfigContext) -> LoadResult:
        """Load config from PADDOCK_* environment variables.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``,
            with empty meta (env carries no ``[config]`` section). Returns an
            empty valid instance when no relevant env vars are present.
            Returns an invalid instance when env-shape validation fails.
        """
        raw_env = {
            k: v for k, v in context.environ.items() if k.startswith(self.PREFIX)
        }

        no_env_form_runner = f.FilterRunner(self._no_env_form_schema(raw_env), raw_env)
        if not no_env_form_runner.is_valid():
            return LoadResult(no_env_form_runner, {})

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

    def _no_env_form_schema(self, raw_env: dict[str, str]) -> f.FilterMapper:
        """Builds a schema rejecting the names in ``raw_env`` that target a
        field with no env form.

        Built per call because the ``_<NAME>``-suffixed forms can only be
        keyed once the actual names are known; ``FilterMapper`` matches keys
        exactly.
        """
        rejected = {}
        for key, value in raw_env.items():
            # Empty means unset, as for every other PADDOCK_* name.
            if value == "":
                continue
            for name, (field, flag) in self._NO_ENV_FORM.items():
                if key == name or key.startswith(f"{name}_"):
                    rejected[key] = NoEnvForm(field, flag)
        return f.FilterMapper(rejected, allow_extra_keys=True, allow_missing_keys=True)

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
