import json
import logging
import os
import subprocess
import tempfile
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

import filters as f

from paddock.docker.build import BuildPolicy

logger = logging.getLogger("paddock")

# Stands in for the last-pull time of an image present locally that paddock has
# no record of pulling, so every periodic policy reads it as due.
NEVER_PULLED = datetime.min.replace(tzinfo=timezone.utc)


class PullLog:
    """
    Records when paddock last pulled each image, keyed by image reference.

    Docker keeps no reliable last-pull time of its own: ``.Metadata.LastTagTime``
    stays at its zero value after a pull on the classic image store (ADR 013).
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def default_path(environ: Mapping[str, str]) -> Path:
        """
        Return the log's path, ``$XDG_STATE_HOME/paddock/pulls.json``.

        An unset, empty or relative ``XDG_STATE_HOME`` falls back to
        ``~/.local/state``, as the XDG Base Directory spec says.

        Args:
            environ: Environment variable mapping to read ``XDG_STATE_HOME``
                from.

        Returns:
            The path to the log. It may not exist on disk.
        """
        state_home = Path(environ.get("XDG_STATE_HOME", ""))
        if not state_home.is_absolute():
            state_home = Path.home() / ".local" / "state"
        return state_home / "paddock" / "pulls.json"

    def last_pulled_at(self, image: str) -> datetime | None:
        """
        Return when paddock last pulled ``image``, or None without a record.

        Args:
            image: The image reference, as configured.

        Returns:
            The recorded pull time, or ``None`` if there is none or it doesn't
            parse.
        """
        runner = f.FilterRunner(f.Required | f.Datetime(), self._read().get(image))
        return runner.cleaned_data if runner.is_valid() else None

    def record(self, image: str, pulled_at: datetime) -> None:
        """
        Record that paddock pulled ``image`` at ``pulled_at``.

        Writes a temporary file and renames it over the log, so a concurrent
        run reads either the old log or the new one, never a partial write.

        Args:
            image: The image reference, as configured.
            pulled_at: When the pull finished.
        """
        entries = self._read()
        entries[image] = pulled_at.isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", dir=self.path.parent, delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(entries, tmp, indent=2, sort_keys=True)
        try:
            os.replace(tmp.name, self.path)
        except OSError:
            os.unlink(tmp.name)
            raise

    def _read(self) -> dict[str, str]:
        """
        Return the log's entries, or none if it is missing or corrupt.

        A corrupt log reads as empty, deliberately: the cost is one extra pull
        per image, and the next ``record`` rewrites it.
        """
        try:
            entries = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return entries if isinstance(entries, dict) else {}


class ImagePuller:
    """Keeps a registry-hosted image current under a build policy (ADR 013)."""

    def __init__(self, log: PullLog) -> None:
        self.log = log

    def maybe_pull(self, *, policy: BuildPolicy, image: str) -> bool:
        """
        Pull the image if the build policy requires it.

        Raises ``subprocess.CalledProcessError`` when a due pull fails, leaving
        the log untouched, so the next run is still due. A log that can't be
        written only warns.

        Args:
            policy: The configured build policy.
            image: The image reference to pull.

        Returns:
            True if a pull ran, False if skipped.
        """
        last_at = None
        if self.image_exists(image):
            last_at = self.log.last_pulled_at(image) or NEVER_PULLED
        if not policy.is_due(last_at):
            return False
        logger.info("Pulling %s (build.policy = %s)", image, policy)
        subprocess.run(["docker", "pull", image], check=True)
        # An unwritable log costs a redundant pull next time, not this run.
        try:
            self.log.record(image, datetime.now(timezone.utc))
        except OSError as e:
            logger.warning("Couldn't record the pull in %s: %s", self.log.path, e)
        return True

    def image_exists(self, image: str) -> bool:
        """Return whether an image named ``image`` exists locally."""
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
