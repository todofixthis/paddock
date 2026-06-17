from pathlib import Path

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.schema import standard_config_schema, user_config_schema
from paddock.config.sources.base import ConfigSource


def _default_user_config_path() -> Path:
    """Return the default user config path.

    Resolved at call time (not import time) so test isolation by redirecting
    ``$HOME`` works as expected: the test fixture sets ``$HOME`` and any later
    call sees the updated value.
    """
    return Path.home() / ".config" / "paddock" / "config.toml"


class UserConfigSource(ConfigSource):
    """Loads the user-level config from ``context.user_config_path``.

    Returns a :class:`filters.FilterRunner` whose ``cleaned_data`` is the
    standard config object — global ``image``/``agent``/``build``/``network``/
    ``volumes`` only. The ``projects`` and ``config`` sections, while valid in
    the file, are stripped from this source's output. They are consumed by
    other code paths (``ProjectOverridesSource`` and the loader's allowlist
    construction respectively).
    """

    SOURCE_KEY = "user"
    WEIGHT = 20

    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Load user config from ``context.user_config_path``.

        Returns:
            A :class:`filters.FilterRunner` over
            ``standard_config_schema(merged=False)``. If the file does not exist,
            the runner has ``cleaned_data == {}``. If the TOML is invalid, the
            runner is not valid.
        """
        path = context.user_config_path
        schema = standard_config_schema(merged=False)
        if not path.exists():
            return f.FilterRunner(schema, {})

        content = path.read_text(encoding="utf-8")
        full_runner = f.FilterRunner(user_config_schema, content)
        if not full_runner.is_valid():
            return full_runner

        cleaned = full_runner.cleaned_data
        stripped = {k: v for k, v in cleaned.items() if k not in {"projects", "config"}}
        return f.FilterRunner(schema, stripped)
