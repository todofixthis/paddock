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

        is_dir:

            When ``True``, the path must be a directory. When ``False``,
            the path must not be a directory. ``None`` (default) skips the
            check. The check is only applied when the path exists on disk.

        must_exist:

            When ``True``, or when ``None`` and ``home_dir`` was not
            supplied, the path must exist. If ``resolve`` is also effective,
            this sets ``strict=True`` on ``.resolve()``; otherwise an
            explicit ``.exists()`` check is used.

        resolve:

            When ``True``, or when ``None`` and ``home_dir`` was not
            supplied, calls ``.resolve()`` on the resulting path. If the path
            fails to resolve, the value is invalid.
    """

    CODE_DOES_NOT_EXIST = "does_not_exist"
    CODE_IS_A_DIRECTORY = "is_a_directory"
    CODE_NOT_A_DIRECTORY = "not_a_directory"

    templates = {
        CODE_DOES_NOT_EXIST: "Path {value!r} does not exist or cannot be resolved.",
        CODE_IS_A_DIRECTORY: "Expected a file, but {value!r} is a directory.",
        CODE_NOT_A_DIRECTORY: "Expected a directory, but {value!r} is not a directory.",
    }

    def __init__(
        self,
        home_dir: str | Path | None = None,
        is_dir: bool | None = None,
        must_exist: bool | None = None,
        resolve: bool | None = None,
    ):
        super().__init__()
        self._home_dir = Path(home_dir) if home_dir is not None else None
        self._is_dir = is_dir
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

        if self._is_dir is not None and path.exists():
            if self._is_dir and not path.is_dir():
                return self._invalid_value(value, self.CODE_NOT_A_DIRECTORY)
            if not self._is_dir and path.is_dir():
                return self._invalid_value(value, self.CODE_IS_A_DIRECTORY)

        return path


class Volume(BaseFilter):
    """Validates a Docker volume container path spec.

    Accepts paths of the form ``/container/path``, ``/container/path:ro``,
    or ``/container/path:rw``. Values with more than one colon-separated
    segment are invalid. Bare paths (no mode suffix) are normalised to
    ``:ro``.

    When ``home_dir`` is supplied, a leading ``~`` in the path portion is
    expanded relative to that directory via ``Filepath``.

    Args:
        home_dir:

            Home directory to substitute for ``~`` in the path portion.
            When ``None`` (default), no tilde expansion is performed.
    """

    CODE_INVALID = "invalid"

    templates = {
        CODE_INVALID: "Expected a container path, optionally suffixed with :ro or :rw.",
    }

    def __init__(self, home_dir: str | Path | None = None):
        super().__init__()
        self._home_dir = Path(home_dir) if home_dir is not None else None

    def _apply(self, value):
        value = cast(str, self._filter(value, f.Unicode))
        if self._has_errors:
            return None

        # Values with more than one colon are invalid.
        parts = value.split(":")
        if len(parts) > 2:
            return self._invalid_value(value, self.CODE_INVALID)

        # If a mode suffix is present, it must be 'ro' or 'rw'.
        if len(parts) == 2 and parts[1] not in ("ro", "rw"):
            return self._invalid_value(value, self.CODE_INVALID)

        mode = ":" + parts[1] if len(parts) == 2 else ":ro"
        path_str = parts[0]

        if self._home_dir is not None:
            path = cast(Path, self._filter(path_str, Filepath(home_dir=self._home_dir)))
            if self._has_errors:
                return None
            return str(path) + mode

        return path_str + mode


class VolumeMap(BaseFilter):
    """Validates a volumes mapping from host paths to container path specs.

    Keys (host paths) are validated through ``f.Unicode | Filepath`` —
    tilde-expanded using ``Path.home()``, resolved, and checked for
    existence. Values (container path specs) are validated through
    ``Volume``.

    Returns a ``dict[str, str]`` mapping resolved host-path strings to
    container path specs.

    Args:
        container_home_dir:

            Home directory to use for tilde expansion in container path
            specs. When ``None`` (default), container paths are validated
            for format only without tilde expansion.
    """

    def __init__(self, container_home_dir: str | Path | None = None):
        super().__init__()
        self._container_home_dir = (
            Path(container_home_dir) if container_home_dir is not None else None
        )

    def _apply(self, value):
        value = cast(dict, self._filter(value, f.Type(dict)))
        if self._has_errors:
            return None

        result = {}
        for raw_host, raw_container in value.items():
            sub_key = str(raw_host)
            host_path = cast(
                Path | None,
                self._filter(raw_host, f.Unicode | Filepath(), sub_key=sub_key),
            )
            container_spec = cast(
                str | None,
                self._filter(
                    raw_container,
                    Volume(home_dir=self._container_home_dir),
                    sub_key=sub_key,
                ),
            )
            if host_path is not None:
                result[str(host_path)] = container_spec

        return result if not self._has_errors else None
