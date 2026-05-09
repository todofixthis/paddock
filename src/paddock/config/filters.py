from pathlib import Path
from typing import cast

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


class Filepath(BaseFilter):
    """Expands a tilde prefix and returns a ``Path``.

    Accepts ``str`` or ``Path`` input. Place after ``f.Unicode`` in a chain
    — this filter asserts the type without coercing it.

    The ``resolve`` and ``must_exist`` parameters default to ``None``, which
    activates them automatically when no custom ``home_dir`` is supplied (host
    paths). Providing a ``home_dir`` disables both by default, because
    container paths cannot be resolved or checked from the host.

    Args:
        home_dir:

            Home directory to substitute for ``~``. When ``None``,
            ``Path.home()`` is used at apply time.

        resolve:

            When ``True``, or when ``None`` and ``home_dir`` was not
            supplied, calls ``.resolve()`` on the resulting path. If the path
            fails to resolve, the value is invalid.

        must_exist:

            When ``True``, or when ``None`` and ``home_dir`` was not
            supplied, the path must exist. If ``resolve`` is also effective,
            this sets ``strict=True`` on ``.resolve()``; otherwise an
            explicit ``.exists()`` check is used.
    """

    CODE_DOES_NOT_EXIST = "does_not_exist"

    templates = {
        CODE_DOES_NOT_EXIST: "Path {value!r} does not exist or cannot be resolved.",
    }

    def __init__(
        self,
        home_dir: str | Path | None = None,
        resolve: bool | None = None,
        must_exist: bool | None = None,
    ):
        super().__init__()
        self._home_dir = Path(home_dir) if home_dir is not None else None
        self._should_resolve = resolve is True or (resolve is None and home_dir is None)
        self._must_exist = must_exist is True or (
            must_exist is None and home_dir is None
        )

    def _apply(self, value):
        value = cast(str | Path, self._filter(value, f.Type((str, Path))))
        if self._has_errors:
            return None

        path = Path(value)
        home = self._home_dir if self._home_dir is not None else Path.home()

        if path.parts and path.parts[0] == "~":
            path = Path(home, *path.parts[1:])

        if self._should_resolve:
            try:
                path = path.resolve(strict=self._must_exist)
            except OSError:
                return self._invalid_value(value, self.CODE_DOES_NOT_EXIST)
        elif self._must_exist:
            if not path.exists():
                return self._invalid_value(value, self.CODE_DOES_NOT_EXIST)

        return path
