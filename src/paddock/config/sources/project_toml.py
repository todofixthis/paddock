from pathlib import Path

import filters as f

from paddock.config.context import ConfigContext
from paddock.config.project_dir import PROJECT_DIR_NAME
from paddock.config.schema import standard_config_schema
from paddock.config.sources.base import ConfigSource, Discarded, LoadResult

_CONFIG_NAME = Path(PROJECT_DIR_NAME) / "config.toml"


class ProjectTomlSource(ConfigSource):
    """Loads ``<workdir>/.paddock/config.toml``.

    Loading is unconditional — gating by the allowlist happens generically in
    the loader's sanitise phase, so even a disabled source can still be
    inspected for warning purposes.
    """

    SOURCE_KEY = "project_toml"
    WEIGHT = 10
    ALLOWLIST_DEFAULT = False

    # Why each kind of key is discarded (ADR 020), completing the loader's
    # "ignored <path> — <reason>" warning.
    USER_ONLY_REASON = "only your user config may set it"
    SERVER_SETTINGS_REASON = (
        "server settings are read only from the global section of your user config"
    )

    def load(self, context: ConfigContext) -> LoadResult:
        """Load config from ``<workdir>/.paddock/config.toml``.

        Returns:
            A :class:`LoadResult` over ``standard_config_schema(merged=False)``,
            with empty meta (project TOML carries no ``[config]`` section).
            Returns an empty valid instance when the file is absent.
        """
        # Relative paths belong to the project, not .paddock/ (ADR 012).
        schema = standard_config_schema(base_dir=context.workdir, merged=False)
        path = context.workdir / _CONFIG_NAME
        if not path.exists():
            return LoadResult(f.FilterRunner(schema, {}), {})

        text = path.read_text(encoding="utf-8")
        decoded = f.FilterRunner(f.TomlDecode, text)
        if not decoded.is_valid():
            return LoadResult(f.FilterRunner(f.TomlDecode | schema, text), {})

        data = dict(decoded.cleaned_data)
        discarded = [
            *self._discard_user_only_sections(data),
            *self._discard_server_settings(data),
        ]
        return LoadResult(f.FilterRunner(schema, data), {}, discarded)

    def _discard_user_only_sections(self, data: dict) -> list[Discarded]:
        """Remove the sections only the user config may hold (ADR 020).

        A committed file cannot grant itself access or configure other
        projects, and must not be able to stop a run by trying, so ``config``
        and ``projects`` go before validation, whatever they contain.

        Args:
            data: The decoded project file, changed in place.

        Returns:
            Each section removed, and why.
        """
        discarded: list[Discarded] = []
        for key in sorted(self._META_SECTION_KEYS):
            if key in data:
                del data[key]
                discarded.append(Discarded(key, self.USER_ONLY_REASON))
        return discarded

    def _discard_server_settings(self, data: dict) -> list[Discarded]:
        """Remove every ``agents.<name>.server`` from decoded project config.

        A project file may never set a shared server's settings, whatever the
        allowlist grants, and must not be able to stop a run by getting them
        wrong, so they go before validation (ADR 019). Anything that is not
        the expected table is left for validation to report.

        Args:
            data: The decoded project file; ``agents`` is replaced by a copy
                without the server settings.

        Returns:
            Each table removed, and why.
        """
        agents = data.get("agents")
        if not isinstance(agents, dict):
            return []

        discarded: list[Discarded] = []
        kept: dict = {}
        for name, settings in agents.items():
            if isinstance(settings, dict) and "server" in settings:
                settings = {k: v for k, v in settings.items() if k != "server"}
                discarded.append(
                    Discarded(f"agents.{name}.server", self.SERVER_SETTINGS_REASON)
                )
            kept[name] = settings
        data["agents"] = kept
        return discarded
