import sys

import filters as f

from paddock.config.filters import Agent, Volume

BUILD_POLICIES = ("always", "daily", "if-missing", "weekly")

# Schema for the build sub-dict.
_build_schema = f.FilterMapper(
    {
        "args": f.Optional(None) | f.FilterRepeater(f.Unicode),
        "context": f.Optional(None),
        "dockerfile": f.Required | f.Unicode | f.NotEmpty,
        "policy": f.Optional(None) | f.Choice(BUILD_POLICIES),
    },
    allow_extra_keys=False,
)

# Top-level config schema — exported for use by the loader.
_config_schema = f.FilterMapper(
    {
        "agent": f.Required | Agent,
        "build": f.Optional(None) | _build_schema,
        "image": f.Required | f.Unicode | f.NotEmpty,
        "network": f.Optional(None),
        "volumes": f.Optional(dict) | f.FilterRepeater(Volume),
    },
    allow_extra_keys=False,
)


class ConfigSchema:
    """Validates a merged paddock config dict.

    Prints errors to stderr and calls ``sys.exit(1)`` on failure.
    """

    def validate(self, config: dict) -> dict:
        """Validates the config dict and returns the cleaned result.

        Args:
            config:

                The raw config mapping to validate.

        Returns:
            The cleaned and normalised config dict.
        """
        runner = f.FilterRunner(_config_schema, config)

        if not runner.is_valid():
            for key, messages in runner.errors.items():
                for msg in messages:
                    print(
                        f"Config error [{key}]: {msg['message']}",
                        file=sys.stderr,
                    )
            sys.exit(1)

        return runner.cleaned_data
