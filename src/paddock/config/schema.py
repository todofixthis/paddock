import sys
from pathlib import Path
from typing import cast

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


def _build_schema(base_dir: Path):
    """Build-section schema; every field is optional.

    A ``policy`` without a ``dockerfile`` pulls the image instead of building
    it (ADR 012).
    """
    return f.FilterMapper(
        {
            "args": f.FilterRepeater(f.Unicode),
            "context": f.Unicode | Filepath(base_dir=base_dir, is_dir=True),
            "dockerfile": (
                f.NotEmpty(allow_none=True)
                | f.Unicode
                | Filepath(base_dir=base_dir, is_dir=False)
            ),
            "policy": f.Choice(BUILD_POLICIES),
        },
        allow_extra_keys=False,
        allow_missing_keys=True,
    )


def _standard_fields(merged: bool, base_dir: Path) -> dict[str, object]:
    """Top-level standard config fields. Mode-aware.

    In merged mode required fields disallow ``None``; in per-source mode they
    allow ``None`` so sources can be incomplete without false errors.
    ``base_dir`` anchors relative host paths (see ``standard_config_schema``).
    """
    return {
        "agent": f.NotEmpty(allow_none=not merged) | Agent,
        "build": _build_schema(base_dir),
        "image": f.NotEmpty(allow_none=not merged) | f.Unicode,
        "network": f.Unicode,
        "volumes": (
            f.Optional({} if merged else None)
            | VolumeMap(container_home_dir=CONTAINER_HOME, host_base_dir=base_dir)
        ),
    }


@filter_macro
def standard_config_schema(
    *,
    base_dir: Path,
    extra_keys: dict | None = None,
    merged: bool = False,
):
    """Macro returning the standard-config filter chain.

    Args:
        base_dir: Directory relative host paths (``build.context``,
            ``build.dockerfile``, ``volumes`` keys) resolve against: the
            workdir the config applies to (ADR 012). Required, so a new
            source can't fall back to the cwd by omission.
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
    fields = _standard_fields(merged, base_dir)
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


@filter_macro
def project_entry_schema(project: str | Path):
    """Macro validating one ``[projects."<path>"]`` entry (per-source).

    Allows ``[config]`` as well as the standard config fields. Relative host
    paths resolve against ``project``, the directory the entry configures
    (ADR 012).

    Args:
        project: The entry's project path, i.e. its key under ``[projects]``.
    """
    return standard_config_schema(
        extra_keys={"config": config_meta_schema},
        merged=False,
        base_dir=Path(project),
    )


class ProjectMap(BaseFilter):
    """Validates ``[projects]``, each entry against its own project path.

    Unlike ``f.FilterRepeater``, the schema varies per key: an entry's relative
    paths resolve against that entry's key, not the project being run.
    """

    def _apply(self, value):
        value = cast(dict, self._filter(value, f.Type(dict)))
        if self._has_errors:
            return None

        result = {
            key: self._filter(entry, project_entry_schema(key), sub_key=str(key))
            for key, entry in value.items()
        }
        return result if not self._has_errors else None


@filter_macro
def user_config_schema(base_dir: Path):
    """Macro validating a whole user config file, from its TOML text.

    Args:
        base_dir: Directory relative host paths in the file's global section
            resolve against: the workdir (ADR 012). Each ``[projects]`` entry
            resolves against its own key instead, the workdir it applies to.
    """
    return f.TomlDecode | f.FilterMapper(
        {
            **_standard_fields(merged=False, base_dir=base_dir),
            "config": config_meta_schema,
            "projects": f.Optional(dict) | ProjectMap,
        },
        allow_extra_keys=False,
        allow_missing_keys=True,
    )


class ConfigSchema:
    """Validates a merged paddock config dict (final-merge pass).

    Thin wrapper around ``standard_config_schema(merged=True)`` for
    backwards-compatible call sites. The loader uses the same schema directly.
    """

    def validate(self, config: dict, *, base_dir: Path) -> dict:
        """Validates the config dict and returns the cleaned result.

        Args:
            config: The raw config mapping to validate.
            base_dir: The workdir relative host paths resolve against
                (ADR 012). Required, as for ``standard_config_schema``.

        Returns:
            The cleaned and normalised config dict.
        """
        runner = f.FilterRunner(
            standard_config_schema(base_dir=base_dir, merged=True), config
        )
        if not runner.is_valid():
            for key, messages in runner.errors.items():
                for msg in messages:
                    print(
                        f"Config error [{key}]: {msg['message']}",
                        file=sys.stderr,
                    )
            sys.exit(1)
        return runner.cleaned_data
