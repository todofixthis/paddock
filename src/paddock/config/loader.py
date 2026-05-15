import sys
from pathlib import Path
from typing import Any, TypedDict

import filters as f

from paddock.config.schema import _config_schema, _env_schema

_USER_CONFIG_PATH = Path.home() / ".config" / "paddock" / "config.toml"
_PROJECT_CONFIG_NAME = Path(".paddock") / "config.toml"


class ConfigEntry(TypedDict):
    """A single config value annotated with its origin."""

    value: Any
    source: str


# SourcedConfig: same shape as the config schema, but leaf values are ConfigEntry.
SourcedConfig = dict[str, Any]


class ConfigError(Exception):
    """Raised when config loading or validation fails."""


class ConfigLoader:
    """Loads, merges, and validates paddock config from all sources.

    Config resolution order (later sources overwrite earlier):

    1. User-level (``~/.config/paddock/config.toml``)
    2. Project-level (``<workdir>/.paddock/config.toml``)
    3. Extra config file via ``PADDOCK_CONFIG_FILE`` env var
    4. Extra config file via ``--config-file`` CLI arg
    5. Env var overrides (``PADDOCK_*``)
    6. CLI arg overrides
    """

    def load_user_config(self, path: Path = _USER_CONFIG_PATH) -> SourcedConfig:
        """Load the user-level config file.

        Args:
            path:

                Path to the user config file. Defaults to
                ``~/.config/paddock/config.toml``.

        Returns:
            A ``SourcedConfig`` mapping, or ``{}`` if the file does not exist.
        """
        return self._load_toml_sourced(path)

    def load_project_config(self, workdir: Path) -> SourcedConfig:
        """Load the project-level config from ``<workdir>/.paddock/config.toml``.

        Args:
            workdir:

                The project working directory.

        Returns:
            A ``SourcedConfig`` mapping, or ``{}`` if the file does not exist.
        """
        return self._load_toml_sourced(workdir / _PROJECT_CONFIG_NAME)

    def load_extra_config(self, path: Path) -> SourcedConfig:
        """Load an arbitrary config file (for ``PADDOCK_CONFIG_FILE`` or ``--config-file``).

        Args:
            path:

                Path to the extra config file.

        Returns:
            A ``SourcedConfig`` mapping, or ``{}`` if the file does not exist.
        """
        return self._load_toml_sourced(path)

    def config_from_env(self, environ: dict[str, str]) -> SourcedConfig:
        """Extract config from ``PADDOCK_*`` environment variables.

        Strips the ``PADDOCK_`` prefix, lowercases, and splits on ``_`` to map
        to the config structure. For example::

            PADDOCK_IMAGE=foo           → {'image': {'value': 'foo', ...}}
            PADDOCK_BUILD_DOCKERFILE=x  → {'build': {'dockerfile': {'value': 'x', ...}}}

        Args:
            environ:

                Environment variable mapping to inspect.

        Returns:
            A ``SourcedConfig`` containing only the ``PADDOCK_``-prefixed entries.
        """
        config: SourcedConfig = {}
        prefix = "PADDOCK_"
        for key, value in environ.items():
            if not key.startswith(prefix):
                continue
            parts = key[len(prefix) :].lower().split("_")
            self._deep_set_sourced(config, parts, value, source=f"env:{key}")
        return config

    def config_from_cli(self, parsed: Any) -> SourcedConfig:
        """Extract config from a parsed CLI args object (omitting ``None`` values).

        Args:
            parsed:

                An object with attributes matching the paddock CLI argument names.

        Returns:
            A ``SourcedConfig`` containing only the non-``None`` CLI values.
        """
        config: SourcedConfig = {}
        build: SourcedConfig = {}
        source = "cli"

        if parsed.image is not None:
            config["image"] = {"value": parsed.image, "source": source}
        if parsed.agent is not None:
            config["agent"] = {"value": parsed.agent, "source": source}
        if parsed.network is not None:
            config["network"] = {"value": parsed.network, "source": source}
        if parsed.build_dockerfile is not None:
            build["dockerfile"] = {"value": parsed.build_dockerfile, "source": source}
        if parsed.build_context is not None:
            build["context"] = {"value": parsed.build_context, "source": source}
        if parsed.build_policy is not None:
            build["policy"] = {"value": parsed.build_policy, "source": source}
        if parsed.build_args:
            build["args"] = {
                k: {"value": v, "source": source} for k, v in parsed.build_args.items()
            }
        if build:
            config["build"] = build
        if parsed.volumes:
            config["volumes"] = {
                k: {"value": v, "source": source} for k, v in parsed.volumes.items()
            }
        return config

    def resolve(
        self,
        parsed: Any,
        workdir: Path,
        environ: dict[str, str] | None = None,
    ) -> f.FilterRunner:
        """Load config from all sources, merge, apply defaults, and validate.

        Args:
            parsed:

                Parsed CLI arguments object.

            workdir:

                The project working directory.

            environ:

                Environment variable mapping. Defaults to ``os.environ``.

        Returns:
            A ``FilterRunner`` for the caller to check ``is_valid()``.
        """
        import os

        env = environ if environ is not None else dict(os.environ)

        env_runner = f.FilterRunner(_env_schema, env)
        if not env_runner.is_valid():
            for key, messages in env_runner.errors.items():
                for msg in messages:
                    print(
                        f"Config error [{key}]: {msg['message']}",
                        file=sys.stderr,
                    )
            sys.exit(1)
        validated_env = env_runner.cleaned_data

        sources = [
            self.load_user_config(),
            self.load_project_config(workdir),
        ]

        if paddock_config_file := validated_env.get("PADDOCK_CONFIG_FILE"):
            sources.append(self.load_extra_config(paddock_config_file))

        if parsed.config_file is not None:
            sources.append(
                self.load_extra_config(Path(parsed.config_file).expanduser())
            )

        # Exclude None values (unset vars), PADDOCK_CONFIG_FILE (meta-key that
        # locates extra config files, not a config value itself), and
        # PADDOCK_BUILD_ARGS (a dict cannot be expressed as a single env var).
        _env_config_exclude = {"PADDOCK_BUILD_ARGS", "PADDOCK_CONFIG_FILE"}
        env_for_config = {
            k: v
            for k, v in validated_env.items()
            if v is not None and k not in _env_config_exclude
        }
        sources.append(self.config_from_env(env_for_config))
        sources.append(self.config_from_cli(parsed))

        merged_sourced = self._merge_sourced(sources)
        plain = self._extract_values(merged_sourced)
        plain = self._apply_defaults(plain)

        return f.FilterRunner(_config_schema, plain)

    def _load_toml_sourced(self, path: Path) -> SourcedConfig:
        """Load a TOML file and wrap each leaf value with its source path.

        Args:
            path:

                Path to the TOML file.

        Returns:
            A ``SourcedConfig``, or ``{}`` if the file does not exist.

        Raises:
            ConfigError: If the file contains invalid TOML.
        """
        if not path.exists():
            return {}
        content = path.read_text(encoding="utf-8")
        runner = f.FilterRunner(f.TomlDecode, content)
        if not runner.is_valid():
            msgs = [e["message"] for errs in runner.errors.values() for e in errs]
            raise ConfigError(f"Invalid TOML in {path}: {'; '.join(msgs)}")
        return self._annotate_source(runner.cleaned_data, str(path))

    def _annotate_source(self, data: dict, source: str) -> SourcedConfig:
        """Recursively wrap leaf values with source info.

        Args:
            data:

                Raw config dict to annotate.

            source:

                Source label (typically a file path string).

        Returns:
            A ``SourcedConfig`` with the same structure as ``data``.
        """
        result: SourcedConfig = {}
        for key, value in data.items():
            if isinstance(value, dict):
                result[key] = self._annotate_source(value, source)
            else:
                result[key] = {"value": value, "source": source}
        return result

    def _deep_set_sourced(
        self,
        config: SourcedConfig,
        parts: list[str],
        value: str,
        source: str,
    ) -> None:
        """Deep-set a value in a ``SourcedConfig`` using a key-path list.

        Args:
            config:

                The target ``SourcedConfig`` to mutate.

            parts:

                Ordered key segments forming the path to the target leaf.

            value:

                The raw string value to store.

            source:

                Source label for the ``ConfigEntry``.
        """
        node = config
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = {"value": value, "source": source}

    def _merge_sourced(self, sources: list[SourcedConfig]) -> SourcedConfig:
        """Deep-merge a list of ``SourcedConfig`` dicts; later sources overwrite earlier.

        Args:
            sources:

                Ordered list of ``SourcedConfig`` mappings.

        Returns:
            A single merged ``SourcedConfig``.
        """
        result: SourcedConfig = {}
        for source in sources:
            result = self._deep_merge(result, source)
        return result

    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Recursively merge ``override`` into ``base``.

        ``ConfigEntry`` dicts (those with both ``value`` and ``source`` keys) are
        treated as leaves and replaced wholesale rather than merged.

        Args:
            base:

                The base dict to merge into.

            override:

                The dict whose values take precedence.

        Returns:
            A new merged dict.
        """
        result = dict(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
                and not ("value" in value and "source" in value)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _extract_values(self, sourced: SourcedConfig) -> dict:
        """Strip source annotations, returning a plain config dict.

        Args:
            sourced:

                A ``SourcedConfig`` to strip.

        Returns:
            A plain dict with the same structure but without ``ConfigEntry`` wrappers.
        """
        result: dict = {}
        for key, value in sourced.items():
            if isinstance(value, dict):
                if "value" in value and "source" in value:
                    result[key] = value["value"]
                else:
                    result[key] = self._extract_values(value)
            else:
                result[key] = value
        return result

    def _apply_defaults(self, config: dict) -> dict:
        """Apply default values for omitted config keys.

        Mutates and returns ``config``.

        Args:
            config:

                The plain config dict to fill.

        Returns:
            The same dict with defaults applied.
        """
        config.setdefault("agent", "claude")
        config.setdefault("build", None)
        config.setdefault("network", None)
        config.setdefault("volumes", {})
        if isinstance(config.get("build"), dict):
            config["build"].setdefault("args", {})
            config["build"].setdefault("context", None)
            config["build"].setdefault("policy", "if-missing")
        return config
