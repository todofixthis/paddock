import logging
from pathlib import Path

from paddock.config.errors import ConfigError
from paddock.config.filters import VolumeSpec

logger = logging.getLogger("paddock")

# Name of the per-project directory paddock manages and mounts. Shared with
# ``ProjectTomlSource`` so the directory name is defined in exactly one place.
PROJECT_DIR_NAME = ".paddock"


class ProjectDirManager:
    """Manages the ``.paddock`` directory lifecycle.

    When project-level config loading is enabled, paddock ensures ``.paddock``
    exists as a directory and mounts it into the container at the same absolute
    path (host == container). After the container exits, paddock removes the
    directory only if it created it and it remains empty.
    """

    def prepare(self, workdir: Path, *, readonly: bool) -> tuple[str, VolumeSpec, bool]:
        """Ensure ``.paddock`` exists and return its mount spec.

        Creates the directory if it does not exist. Raises if the path exists
        but is not a directory.

        Args:
            workdir: The project working directory.
            readonly: When ``True``, the volume is mounted read-only (``ro``);
                otherwise read-write (``rw``).

        Returns:
            A 3-tuple of ``(host_path, VolumeSpec, created)`` where
            ``host_path`` is the absolute path string, ``VolumeSpec``
            carries the container mount spec, and ``created`` is ``True``
            when paddock created the directory in this call.

        Raises:
            ConfigError: When ``.paddock`` exists but is not a directory.
        """
        paddock_dir = workdir / PROJECT_DIR_NAME
        if paddock_dir.exists() and not paddock_dir.is_dir():
            raise ConfigError(
                f"{paddock_dir} exists but is not a directory; "
                "paddock cannot mount it as the project config directory"
            )
        created = False
        if not paddock_dir.exists():
            paddock_dir.mkdir()
            created = True
        host_path = str(paddock_dir)
        mode = "ro" if readonly else "rw"
        return host_path, VolumeSpec(host_path, mode), created

    def cleanup(self, workdir: Path, *, created_by_paddock: bool) -> None:
        """Remove ``.paddock`` if paddock created it and it is empty.

        If the directory has contents after the container exits, a warning is
        logged and the directory is left in place for manual review.

        Args:
            workdir: The project working directory.
            created_by_paddock: When ``False``, the directory is left
                untouched regardless of its state.
        """
        if not created_by_paddock:
            return
        paddock_dir = workdir / PROJECT_DIR_NAME
        if not paddock_dir.exists():
            return
        if any(paddock_dir.iterdir()):
            logger.warning(
                "%s has contents after container exit — "
                "leaving in place for manual review",
                paddock_dir,
            )
            return
        paddock_dir.rmdir()
