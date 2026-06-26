from typing import cast

import filters as f
from filters.base import BaseFilter


class ExtractProject(BaseFilter):
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

    def _apply(self, value):
        value = cast(dict, self._filter(value, f.Type(dict)))
        if self._has_errors:
            return None
        projects = value.get("projects")
        if not isinstance(projects, dict):
            return {}
        entry = projects.get(self._project)
        return entry if isinstance(entry, dict) else {}
