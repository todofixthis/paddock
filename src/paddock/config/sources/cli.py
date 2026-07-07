from typing import Any

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.schema import standard_config_schema
from paddock.config.sources.base import ConfigSource, LoadResult


class CliConfigSource(ConfigSource):
    """Reads config from parsed CLI arguments (``context.parsed``)."""

    SOURCE_KEY = "cli"
    WEIGHT = 60
    ALLOWLIST_DEFAULT = True

    def load(self, context: ConfigContext) -> LoadResult:
        """Load config from ``context.parsed``.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``,
            with empty meta (CLI carries no ``[config]`` section). Only
            non-``None`` values from ``parsed`` are included.
        """
        parsed = context.parsed
        raw: dict[str, Any] = {}
        build: dict[str, Any] = {}

        if parsed.image is not None:
            raw["image"] = parsed.image
        if parsed.agent is not None:
            raw["agent"] = parsed.agent
        if parsed.network is not None:
            raw["network"] = parsed.network
        if parsed.build_dockerfile is not None:
            build["dockerfile"] = parsed.build_dockerfile
        if parsed.build_context is not None:
            build["context"] = parsed.build_context
        if parsed.build_policy is not None:
            build["policy"] = parsed.build_policy
        if parsed.build_args:
            build["args"] = dict(parsed.build_args)
        if build:
            raw["build"] = build
        if parsed.volumes:
            raw["volumes"] = dict(parsed.volumes)

        return LoadResult(f.FilterRunner(standard_config_schema(merged=False), raw), {})
