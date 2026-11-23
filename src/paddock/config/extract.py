from typing import Any, cast

import filters as f
from filters.base import BaseFilter


class ExtractProject(BaseFilter[dict[str, Any]]):
    """Pick ``[projects."<project>"]`` out of a decoded user-config dict.

    Drops everything else (including ``[config]`` and other projects). When the
    requested project key is absent, returns ``{}``. Input must be a ``dict``;
    output is the inner dict belonging to the requested project, or ``{}``.

    Note:
        Once todofixthis/filters#93 (``f.Item``) and #94 land, this custom
        filter can collapse into a ``filter_macro`` built from
        ``f.Type(dict) | f.Item('projects', default=dict) | f.Item(project,
        default=dict)``, removing the need for a bespoke ``_apply``.

    Args:
        project: Absolute project path string to look up under ``[projects]``.
    """

    def __init__(self, project: str) -> None:
        super().__init__()
        self._project = project

    def _apply(self, value: Any) -> dict[str, Any]:
        value = cast(dict[str, Any], self._filter(value, f.Type(dict)))
        if self._has_errors:
            # phx-filters rejects a value by returning None from a non-Optional
            # `_apply`; drop this ignore once todofixthis/filters#121 makes
            # rejection raise instead.
            return None  # type: ignore[return-value]
        projects = value.get("projects")
        if not isinstance(projects, dict):
            return {}
        entry = projects.get(self._project)
        return cast(dict[str, Any], entry) if isinstance(entry, dict) else {}
