import sys

import filters as f

from paddock.config.filters import Agent, Filepath, Volume

BUILD_POLICIES = ("always", "daily", "if-missing", "weekly")

# Schema for the build sub-dict.
_build_schema = f.FilterMapper(
    {
        "args": f.FilterRepeater(f.Unicode),
        "context": f.Unicode | Filepath,
        "dockerfile": f.Required | f.Unicode | f.NotEmpty | Filepath,
        "policy": f.Choice(BUILD_POLICIES),
    },
    allow_extra_keys=False,
)

# Top-level config schema — exported for use by the loader.
_config_schema = f.FilterMapper(
    {
        "agent": f.Required | Agent,
        "build": _build_schema,
        "image": f.Required | f.Unicode | f.NotEmpty,
        "network": f.Unicode,
        "volumes": f.Optional(dict) | f.FilterRepeater(Volume),
    },
    allow_extra_keys=False,
)

# Flat schema for PADDOCK_* environment variables, validated before mapping.
_env_schema = f.FilterMapper(
    {
        "PADDOCK_AGENT": Agent,
        "PADDOCK_BUILD_CONTEXT": f.Unicode | Filepath,
        "PADDOCK_BUILD_DOCKERFILE": f.Unicode | Filepath,
        "PADDOCK_BUILD_POLICY": f.Choice(BUILD_POLICIES),
        "PADDOCK_CONFIG_FILE": f.Unicode | Filepath,
        "PADDOCK_IMAGE": f.Unicode | f.NotEmpty,
        "PADDOCK_NETWORK": f.Unicode,
    },
    allow_extra_keys=True,
    allow_missing_keys=True,
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
