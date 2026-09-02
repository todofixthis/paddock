import logging
from pathlib import Path

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

        If the directory has contents after the container exits, a warning is
        logged and the directory is left in place for manual review. A
        pre-existing directory is never removed.
        """
        if not self._created or not self._dir.exists():
            return
        if any(self._dir.iterdir()):
            logger.warning(
                "%s has contents after container exit — leaving in place "
                "for manual review",
                self._dir,
            )
            return
        self._dir.rmdir()
