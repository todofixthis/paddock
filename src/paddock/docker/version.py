import json
import subprocess
from typing import ClassVar

from paddock.config.errors import PaddockEnvironmentError


class DockerVersion:
    """Checks that Docker is new enough to run an agent server (ADR 019).

    A paired client is created on two networks, its own and the server's.
    API 1.44, Docker Engine 25.0, is the first whose daemon accepts that;
    an older one refuses the client only after the server has been started.
    """

    MIN_API_VERSION: ClassVar[tuple[int, int]] = (1, 44)
    MIN_ENGINE_VERSION: ClassVar[str] = "25.0"

    @classmethod
    def require_minimum(cls) -> None:
        """Stop unless the Docker client and daemon both meet the minimum.

        Raises:
            PaddockEnvironmentError: If either is older, or the version cannot
                be read, as when no daemon answers.
        """
        result = subprocess.run(
            ["docker", "version", "--format", "{{json .}}"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            versions = json.loads(result.stdout)
            found = min(
                cls._parse(versions[side]["ApiVersion"])
                for side in ("Client", "Server")
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            lines = [line.strip() for line in result.stderr.splitlines()]
            reason = next((line for line in lines if line), "unexpected output")
            raise PaddockEnvironmentError(
                f"[docker] Could not read the Docker version: {reason}"
            ) from None

        if found < cls.MIN_API_VERSION:
            minimum = ".".join(str(part) for part in cls.MIN_API_VERSION)
            raise PaddockEnvironmentError(
                f"[docker] Agent servers need Docker Engine "
                f"{cls.MIN_ENGINE_VERSION} or newer (API {minimum}); found API "
                f"{'.'.join(str(part) for part in found)}"
            )

    @staticmethod
    def _parse(version: str) -> tuple[int, ...]:
        """Split a dotted API version into numbers, so 1.100 beats 1.44."""
        return tuple(int(part) for part in version.split("."))
