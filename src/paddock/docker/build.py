import json
import subprocess
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import filters as f

BUILT_AT_LABEL = "paddock.built-at"


class BuildPolicy(StrEnum):
    ALWAYS = "always"
    DAILY = "daily"
    IF_MISSING = "if-missing"
    WEEKLY = "weekly"


class ImageBuilder:
    @staticmethod
    def should_build(policy: BuildPolicy, image_built_at: datetime | None) -> bool:
        """Determine whether to build the image given the policy and current image age."""
        match policy:
            case BuildPolicy.ALWAYS:
                return True
            case BuildPolicy.IF_MISSING:
                return image_built_at is None
            case BuildPolicy.DAILY:
                if image_built_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_built_at) > timedelta(
                    hours=24
                )
            case BuildPolicy.WEEKLY:
                if image_built_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_built_at) > timedelta(days=7)

    def get_image_built_at(self, image: str) -> datetime | None:
        """
        Return when paddock last built a local Docker image, or None if absent.

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
        for candidate in (labels.get(BUILT_AT_LABEL), inspected.get("Created")):
            runner = f.FilterRunner(f.Required | f.Datetime(), candidate)
            if runner.is_valid():
                return runner.cleaned_data
        return None

    def run_build(
        self,
        *,
        image: str,
        dockerfile: Path,
        context: Path,
        build_args: dict[str, str],
    ) -> None:
        """
        Run docker build, streaming output to stdout.

        Stamps ``BUILT_AT_LABEL`` with the build time, so the image's age
        reads correctly even when every layer comes from the cache.
        """
        built_at = datetime.now(timezone.utc).isoformat()
        argv: list[str | Path] = ["docker", "build", "-t", image, "-f", dockerfile]
        argv += ["--label", f"{BUILT_AT_LABEL}={built_at}"]
        for key, value in build_args.items():
            argv += ["--build-arg", f"{key}={value}"]
        argv.append(context)
        subprocess.run(argv, check=True)

    def maybe_build(
        self,
        *,
        build_config: dict,
        image: str,
        build_args: dict[str, str],
    ) -> bool:
        """
        Build the image if the build policy requires it.

        Returns True if a build was triggered, False if skipped.
        """
        policy = BuildPolicy(build_config.get("policy", "if-missing"))
        dockerfile = build_config["dockerfile"]
        context = build_config.get("context") or dockerfile.parent
        image_built_at = self.get_image_built_at(image)
        if self.should_build(policy, image_built_at):
            self.run_build(
                image=image,
                dockerfile=dockerfile,
                context=context,
                build_args=build_args,
            )
            return True
        return False
