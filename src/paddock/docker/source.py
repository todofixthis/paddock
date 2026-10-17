from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import ClassVar


class BuildPolicy(StrEnum):
    ALWAYS = "always"
    DAILY = "daily"
    IF_MISSING = "if-missing"
    WEEKLY = "weekly"

    def is_due(self, last_at: datetime | None) -> bool:
        """
        Whether the policy calls for a new image, built or pulled.

        Args:
            last_at: When paddock last built or pulled the image, or ``None``
                if no image by that name exists locally.

        Returns:
            True when paddock should build or pull the image before running it.
        """
        match self:
            case BuildPolicy.ALWAYS:
                return True
            case BuildPolicy.IF_MISSING:
                return last_at is None
            case BuildPolicy.DAILY:
                max_age = timedelta(hours=24)
            case BuildPolicy.WEEKLY:
                max_age = timedelta(days=7)
        return last_at is None or datetime.now(timezone.utc) - last_at > max_age


class ImageSource(ABC):
    """Keeps a local image current under a build policy, before a run uses it.

    ``ImageSourceFactory`` picks the implementation from the ``build`` config.
    """

    # Names what a refresh does, for the run's log line ("Image build: …").
    action: ClassVar[str]
    policy: BuildPolicy

    @abstractmethod
    def refresh(self, image: str) -> bool:
        """
        Build or pull ``image`` if the build policy requires it.

        Raises ``subprocess.CalledProcessError`` when Docker fails.

        Args:
            image: The image reference the run uses.

        Returns:
            True if a build or pull ran, False if skipped.
        """
