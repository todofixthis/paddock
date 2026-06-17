from typing import Any

import filters as f

from paddock.config.allowlist import Allowlist
from paddock.config.context import ConfigContext
from paddock.config.schema import standard_config_schema
from paddock.config.sources.base import ConfigSource


class CliConfigSource(ConfigSource):
    """Reads config from parsed CLI arguments (``context.parsed``)."""

    SOURCE_KEY = "cli"
    WEIGHT = 60

    def load(self, context: ConfigContext) -> f.FilterRunner:
        """Load config from ``context.parsed``.

        Returns:
            A :class:`filters.FilterRunner` over
            ``standard_config_schema(merged=False)``. Only non-``None`` values
            from ``parsed`` are included.
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

        return f.FilterRunner(standard_config_schema(merged=False), raw)

    def sanitise(
        self, runner: f.FilterRunner, allowlist: Allowlist | None
    ) -> f.FilterRunner:
        """Drop keys not permitted by the allowlist for this source.

        No-op when ``allowlist`` is ``None``.
        """
        if allowlist is None or not runner.is_valid():
            return runner
        filtered = allowlist.filter(runner.cleaned_data, self.SOURCE_KEY)
        return f.FilterRunner(standard_config_schema(merged=False), filtered)
