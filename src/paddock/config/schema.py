import sys

import filters as f
from filters.base import BaseFilter
from filters.macros import filter_macro

from paddock.config.filters import Agent, AllowlistEntry, Filepath, VolumeMap

BUILD_POLICIES = ("always", "daily", "if-missing", "weekly")
CONTAINER_HOME = "/root"


class DropEmpty(BaseFilter):
    """Recursively strips ``None`` and empty-``dict`` values from a dict.

    Applied after :class:`f.FilterMapper` so that absent fields don't pollute
    the merge phase with ``{"image": None, ...}`` (which would clobber earlier
    sources). Non-dict inputs are returned unchanged.
    """

    def _apply(self, value):
        if not isinstance(value, dict):
            return value
        out: dict = {}
        for key, sub in value.items():
            if sub is None:
                continue
            if isinstance(sub, dict):
                cleaned = self._apply(sub)
                if cleaned:
                    out[key] = cleaned
                continue
            out[key] = sub
        return out


def _build_schema(merged: bool):
    """Build-section schema. ``dockerfile`` is the only required field."""
    return f.FilterMapper(
        {
            "args": f.FilterRepeater(f.Unicode),
            "context": f.Unicode | Filepath(is_dir=True),
            "dockerfile": (
                f.NotEmpty(allow_none=not merged) | f.Unicode | Filepath(is_dir=False)
            ),
            "policy": f.Choice(BUILD_POLICIES),
        },
        allow_extra_keys=False,
        allow_missing_keys=True,
    )


def _standard_fields(merged: bool) -> dict[str, object]:
    """Top-level standard config fields. Mode-aware.

    In merged mode required fields disallow ``None``; in per-source mode they
    allow ``None`` so sources can be incomplete without false errors.
    """
    return {
        "agent": f.NotEmpty(allow_none=not merged) | Agent,
        "build": _build_schema(merged),
        "image": f.NotEmpty(allow_none=not merged) | f.Unicode,
        "network": f.Unicode,
        "volumes": (
            f.Optional({} if merged else None)
            | VolumeMap(container_home_dir=CONTAINER_HOME)
        ),
    }


@filter_macro
def standard_config_schema(extra_keys: dict | None = None, merged: bool = False):
    """Macro returning the standard-config filter chain.

    Args:
        extra_keys: Optional mapping of additional top-level keys to allow
            (e.g. ``{"config": config_meta_schema}``).
        merged: ``False`` (default) is the per-source pass: every required
            field allows ``None``/missing, every optional field defaults to
            ``None``. ``True`` is the final merged pass: required fields reject
            ``None``/empty, optional fields use their conventional defaults.

    Returns:
        A filter chain ``FilterMapper(...) | DropEmpty``. ``DropEmpty`` strips
        ``None``/empty-dict leaves so per-source results merge cleanly.
    """
    fields = _standard_fields(merged)
    if extra_keys:
        fields.update(extra_keys)
    return (
        f.FilterMapper(fields, allow_extra_keys=False, allow_missing_keys=True)
        | DropEmpty
    )


_ALLOWLIST_SOURCES = frozenset({"cli", "env", "project_toml"})

_allowlist_schema = f.FilterMapper(
    # No f.Optional default. NOTE: FilterMapper(allow_missing_keys=True) still
    # runs each filter for a *missing* key with None — AllowlistEntry passes
    # None through (BaseFilter short-circuits), so unset keys surface as
    # value None (not absent). The loader strips those None values before
    # overlaying explicit rules onto class defaults (see _extract_meta).
    {key: AllowlistEntry for key in _ALLOWLIST_SOURCES},
    allow_extra_keys=False,
    allow_missing_keys=True,
)

config_meta_schema = f.FilterMapper(
    {
        "allowlist": _allowlist_schema,
        # Not f.Optional(True): an unset value must stay None so the loader can
        # tell "unset" from an explicit False and fall back correctly. The
        # default True is applied in the loader, presence-aware.
        "project_dir_readonly": f.Type(bool),
    },
    allow_extra_keys=False,
    allow_missing_keys=True,
)


# Per-project overrides allow [projects."<path>".config.allowlist] as well as
# the standard config fields. Per-source (merged=False).
_project_entry_schema = standard_config_schema(
    extra_keys={"config": config_meta_schema}, merged=False
)


user_config_schema = f.TomlDecode | f.FilterMapper(
    {
        **_standard_fields(merged=False),
        "config": config_meta_schema,
        "projects": (f.Optional(dict) | f.FilterRepeater(_project_entry_schema)),
    },
    allow_extra_keys=False,
    allow_missing_keys=True,
)


class ConfigSchema:
    """Validates a merged paddock config dict (final-merge pass).

    Thin wrapper around ``standard_config_schema(merged=True)`` for
    backwards-compatible call sites. The loader uses the same schema directly.
    """

    def validate(self, config: dict) -> dict:
        """Validates the config dict and returns the cleaned result.

        Args:
            config: The raw config mapping to validate.

        Returns:
            The cleaned and normalised config dict.
        """
        runner = f.FilterRunner(standard_config_schema(merged=True), config)
        if not runner.is_valid():
            for key, messages in runner.errors.items():
                for msg in messages:
                    print(
                        f"Config error [{key}]: {msg['message']}",
                        file=sys.stderr,
                    )
            sys.exit(1)
        return runner.cleaned_data
