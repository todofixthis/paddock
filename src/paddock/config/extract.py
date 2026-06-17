from filters.base import BaseFilter


class ExtractProject(BaseFilter):
    """Pick ``[projects."<project>"]`` out of a decoded user-config dict.

    Drops everything else (including ``[config]`` and other projects). When the
    requested project key is absent, returns ``{}``. Input must be a ``dict``;
    output is the inner dict belonging to the requested project, or ``{}``.

    Args:
        project: Absolute project path string to look up under ``[projects]``.
    """

    CODE_NOT_DICT = "not_dict"
    templates = {CODE_NOT_DICT: "Expected a dict at the top level."}

    def __init__(self, project: str) -> None:
        super().__init__()
        self._project = project

    def _apply(self, value):
        if not isinstance(value, dict):
            return self._invalid_value(value, self.CODE_NOT_DICT)
        projects = value.get("projects")
        if not isinstance(projects, dict):
            return {}
        entry = projects.get(self._project)
        return entry if isinstance(entry, dict) else {}
