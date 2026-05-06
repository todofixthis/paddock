import filters as f
from filters.base import BaseFilter


class Agent(BaseFilter):
    """Validates a coding agent value.

    Accepts a non-empty string agent name, or ``False`` to disable the agent.
    Maps the string ``'false'`` to boolean ``False``. Rejects boolean ``True``.
    """

    CODE_INVALID = "invalid"

    templates = {
        CODE_INVALID: "Expected a non-empty agent name string, or False.",
    }

    def _apply(self, value):
        # Boolean True is always invalid.
        if value is True:
            return self._invalid_value(value, self.CODE_INVALID)

        # Boolean False passes through directly.
        if value is False:
            return False

        # Map the string 'false' to boolean False.
        if isinstance(value, str) and value == "false":
            return False

        # Non-empty string agent names are valid.
        value = self._filter(value, f.Unicode | f.NotEmpty)
        if self._has_errors:
            return None

        return value


class Volume(BaseFilter):
    """Validates a Docker volume container path.

    Accepts paths of the form ``/container/path``, ``/container/path:ro``,
    or ``/container/path:rw``. Values with more than one colon-separated
    segment are invalid.
    """

    CODE_INVALID = "invalid"

    templates = {
        CODE_INVALID: "Expected a container path, optionally suffixed with :ro or :rw.",
    }

    def _apply(self, value):
        value = self._filter(value, f.Unicode)
        if self._has_errors:
            return None

        # Values with more than one colon are invalid.
        parts = value.split(":")
        if len(parts) > 2:
            return self._invalid_value(value, self.CODE_INVALID)

        # If a mode suffix is present, it must be 'ro' or 'rw'.
        if len(parts) == 2 and parts[1] not in ("ro", "rw"):
            return self._invalid_value(value, self.CODE_INVALID)

        # Bare paths (no mode suffix) are normalised to read-only.
        if len(parts) == 1:
            return value + ":ro"

        return value
