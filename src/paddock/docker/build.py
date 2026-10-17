import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import filters as f

from paddock.docker.source import BuildPolicy, ImageSource

# Label every paddock build stamps with its UTC build time. Build policies read
# an image's age from it, not from ``.Created`` alone (ADR 011).
BUILT_AT_LABEL = "paddock.built-at"


class ImageBuilder(ImageSource):
    """Keeps an image current by building it from a Dockerfile (ADR 011)."""

    action = "build"

    def __init__(
        self,
        *,
        policy: BuildPolicy,
        dockerfile: Path,
        context: Path,
        build_args: dict[str, str],
    ) -> None:
        self.policy = policy
        self.dockerfile = dockerfile
        self.context = context
        self.build_args = build_args

    def refresh(self, image: str) -> bool:
        """
        Build the image if the build policy requires it.

        Args:
            image: The tag to build.

        Returns:
            True if a build ran, False if skipped.
        """
        if not self.policy.is_due(self.get_image_built_at(image)):
            return False
        self.run_build(image)
        return True

    @staticmethod
    def get_image_built_at(image: str) -> datetime | None:
        """
        Return when paddock last built a local Docker image, or None if absent
        or neither timestamp parses.

        Reads the ``BUILT_AT_LABEL`` that ``run_build`` stamps, falling back
        to ``.Created`` for an image paddock didn't build. ``.Created`` alone
        can't be trusted (ADR 011): a cached build keeps the old value, a
        Dockerfile adding no layer inherits its base's, and
        ``SOURCE_DATE_EPOCH`` pins it.
        """
        result = subprocess.run(
            ["docker", "image", "inspect", "--format={{json .}}", image],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        inspected = json.loads(result.stdout)
        labels = (inspected.get("Config") or {}).get("Labels") or {}
        # A malformed timestamp counts as absent, deliberately: a bad label falls
        # back to ``.Created``, and with neither valid the image reads as missing,
        # so the policy rebuilds it, which is a cheap fix.
        for candidate in (labels.get(BUILT_AT_LABEL), inspected.get("Created")):
            runner = f.FilterRunner(f.Required | f.Datetime(), candidate)
            if runner.is_valid():
                return runner.cleaned_data
        return None

    def run_build(self, image: str) -> None:
        """
        Run docker build, streaming output to stdout.

        Stamps ``BUILT_AT_LABEL`` with the build time, so the image's age
        reads correctly even when every layer comes from the cache.

        Args:
            image: The tag to build.
        """
        built_at = datetime.now(timezone.utc).isoformat()
        argv: list[str | Path] = ["docker", "build", "-t", image, "-f", self.dockerfile]
        argv += ["--label", f"{BUILT_AT_LABEL}={built_at}"]
        for key, value in self.build_args.items():
            argv += ["--build-arg", f"{key}={value}"]
        argv.append(self.context)
        subprocess.run(argv, check=True)
