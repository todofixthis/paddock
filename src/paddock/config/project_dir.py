import logging
from pathlib import Path
from time import sleep

from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec

logger = logging.getLogger("paddock")

# Name of the per-project directory paddock manages and mounts. Shared with
# ``ProjectTomlSource`` so the directory name is defined in exactly one place.
PROJECT_DIR_NAME = ".paddock"


class ProjectDirManager:
    """Context manager for the ``.paddock`` directory lifecycle.

    On enter (when ``enabled``) ensures ``.paddock`` exists and yields its mount
    spec; on exit removes it only if paddock created it and it is still empty.
    When ``enabled`` is ``False`` it is an inert no-op yielding ``None``.
    """

    # Docker Desktop on macOS can deny rmdir with EACCES for a moment after
    # the container exits; measured outside paddock, it cleared within ~50 ms.
    # The window below is a judgement call on that measurement.
    RMDIR_ATTEMPTS = 10
    RMDIR_RETRY_DELAY = 0.1

    def __init__(self, workdir: Path, *, readonly: bool, enabled: bool) -> None:
        """Initialises the manager for a single ``.paddock`` lifecycle.

        Args:
            workdir: The project working directory.
            readonly: When ``True``, the volume is mounted read-only (``ro``);
                otherwise read-write (``rw``).
            enabled: When ``False``, the manager is an inert no-op.
        """
        self._dir = workdir / PROJECT_DIR_NAME
        self._readonly = readonly
        self._enabled = enabled
        self._created = False

    def __enter__(self) -> tuple[str, VolumeSpec] | None:
        """Ensures ``.paddock`` exists and returns its mount spec.

        Creates the directory if it does not exist. Raises if the path is a
        symlink, or exists but is not a directory. Returns ``None`` without
        touching the filesystem when the manager is disabled.

        Returns:
            A 2-tuple of ``(host_path, VolumeSpec)``, or ``None`` when
            disabled.

        Raises:
            PaddockEnvironmentError: When ``.paddock`` is a symlink, or
                exists but is not a directory.
        """
        if not self._enabled:
            return None
        # Checked first because exists()/is_dir() follow the link: a symlinked
        # directory would pass the check below, and a dangling one reports
        # exists() False and falls through to mkdir().
        if self._dir.is_symlink():
            raise PaddockEnvironmentError(
                f"{self._dir} is a symlink; paddock will not mount a symlinked "
                "project config directory"
            )
        if self._dir.exists() and not self._dir.is_dir():
            raise PaddockEnvironmentError(
                f"{self._dir} exists but is not a directory; paddock cannot "
                "mount it as the project config directory"
            )
        if not self._dir.exists():
            self._dir.mkdir()
            self._created = True
        host_path = str(self._dir)
        mode = "ro" if self._readonly else "rw"
        return host_path, VolumeSpec(host_path, mode)

    def __exit__(self, *exc: object) -> None:
        """Removes ``.paddock`` if paddock created it and it is empty.

        If the directory has contents after the container exits, or cannot be
        inspected or removed, a warning is logged and the directory is left in
        place for manual review. A pre-existing directory is never removed.

        Note:
            No ``OSError`` may escape: one raised here would replace the
            ``SystemExit`` carrying the container's exit code.
        """
        if not self._created:
            return
        try:
            if not self._dir.exists():
                return
            has_contents = any(self._dir.iterdir())
        except OSError as e:
            self._warn_left_in_place(f"could not be inspected ({e})")
            return
        if has_contents:
            self._warn_left_in_place("has contents after container exit")
            return
        self._remove_dir()

    def _remove_dir(self) -> None:
        """Removes the empty ``.paddock``, retrying a transient ``EACCES``.

        Gives up with a warning after ``RMDIR_ATTEMPTS`` permission errors or
        on any other ``OSError``. A directory already gone counts as removed.
        """
        for attempt in range(1, self.RMDIR_ATTEMPTS + 1):
            try:
                self._dir.rmdir()
                return
            except FileNotFoundError:
                return
            except PermissionError as e:
                if attempt == self.RMDIR_ATTEMPTS:
                    self._warn_left_in_place(f"could not be removed ({e})")
                    return
                sleep(self.RMDIR_RETRY_DELAY)
            except OSError as e:
                self._warn_left_in_place(f"could not be removed ({e})")
                return

    def _warn_left_in_place(self, reason: str) -> None:
        """Logs that ``.paddock`` is being left in place, and why.

        Args:
            reason: What went wrong, phrased to follow the directory path.
        """
        logger.warning("%s %s — leaving in place for manual review", self._dir, reason)
