from pathlib import Path
from typing import Any, ClassVar

import filters as f
from filters.macros import filter_macro

from paddock.config.context import ConfigContext
from paddock.config.filters import Agent, Filepath
from paddock.config.schema import BUILD_POLICIES, standard_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult


# Validates the raw PADDOCK_* shape, and is the complete list of PADDOCK_*
# names; any other name is an error. ``load`` maps a name to its config path by
# splitting on ``_``, so a directive with ``_`` in its own name (e.g.
# ``config.project_dir_readonly``) needs more than an entry here. The free-form
# maps (``build.args``, ``volumes``) have no env form: their keys are user data
# that the split would break up, and a name's case is lost.
@filter_macro
def _env_schema(base_dir: Path):
    """Macro validating the raw ``PADDOCK_*`` shape.

    Args:
        base_dir: Directory relative paths resolve against: the workdir, as
            for every source (ADR 012).
    """
    return f.FilterMapper(
        {
            "PADDOCK_AGENT": Agent,
            "PADDOCK_BUILD_CONTEXT": (
                f.Unicode | f.NotEmpty | Filepath(base_dir=base_dir, is_dir=True)
            ),
            "PADDOCK_BUILD_DOCKERFILE": (
                f.Unicode | f.NotEmpty | Filepath(base_dir=base_dir, is_dir=False)
            ),
            "PADDOCK_BUILD_POLICY": f.Choice(BUILD_POLICIES),
            "PADDOCK_IMAGE": f.Unicode | f.NotEmpty,
            "PADDOCK_NETWORK": f.Unicode,
        },
        allow_extra_keys=False,
        allow_missing_keys=True,
    )


class EnvConfigSource(ConfigSource):
    """Reads config from ``PADDOCK_*`` environment variables.

    Owns the entire env-vars pipeline:

    1. Filter ``context.environ`` down to the ``PADDOCK_*`` subset.
    2. Validate names and values via the private ``_env_schema``, resolving
       relative paths against the workdir.
    3. Transform the validated PADDOCK_*-keyed dict into the standard config
       shape (``PADDOCK_BUILD_DOCKERFILE`` → ``build.dockerfile``).
    4. Run the result through ``standard_config_schema(merged=False)`` so the
       returned runner is shape-compatible with every other source.
    """

    SOURCE_KEY = "env"
    WEIGHT = 50
    ALLOWLIST_DEFAULT = True
    PREFIX: ClassVar[str] = "PADDOCK_"

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

        env_runner = f.FilterRunner(_env_schema(context.workdir), raw_env)
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
            f.FilterRunner(
                standard_config_schema(base_dir=context.workdir, merged=False),
                shaped,
            ),
            {},
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
