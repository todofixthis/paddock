import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import filters as f

logger = logging.getLogger(__name__)

REFRESHED_AT_LABEL = "paddock.refreshed-at"


class BuildPolicy(StrEnum):
    ALWAYS = "always"
    DAILY = "daily"
    IF_MISSING = "if-missing"
    WEEKLY = "weekly"

    @property
    def refreshes(self) -> bool:
        """
        Whether builds under this policy bypass the layer cache (ADR 011).

        Periodic policies exist to pick up upstream changes — a new agent
        release, base image updates — which a cached build replays instead.
        """
        return self in (BuildPolicy.DAILY, BuildPolicy.WEEKLY)


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
        Return when a local Docker image was last built, or None if absent.

        Reads the ``REFRESHED_AT_LABEL`` a refresh build stamps, falling back
        to ``.Created`` for an image paddock never refreshed. ``.Created``
        alone can't be trusted (ADR 011): a cached build keeps the old value,
        a Dockerfile adding no layer inherits its base's, and
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
        for candidate in (labels.get(REFRESHED_AT_LABEL), inspected.get("Created")):
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
        refresh: bool = False,
    ) -> None:
        """
        Run docker build, streaming output to stdout.

        Args:
            image: Tag to build.
            dockerfile: Path to the Dockerfile.
            context: Build context directory.
            build_args: ``--build-arg`` values.
            refresh: Skip the layer cache and pull the base image, so every
                layer reruns against current upstreams, and stamp the
                ``REFRESHED_AT_LABEL`` that ``get_image_built_at`` reads.
        """
        argv: list[str | Path] = ["docker", "build", "-t", image, "-f", dockerfile]
        if refresh:
            refreshed_at = datetime.now(timezone.utc).isoformat()
            argv += [
                "--no-cache",
                "--pull",
                "--label",
                f"{REFRESHED_AT_LABEL}={refreshed_at}",
            ]
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

        Returns True if a build ran, False if skipped. A failed refresh of an
        existing image logs a warning and returns False, leaving that image to
        run (ADR 011); any other failed build raises.
        """
        policy = BuildPolicy(build_config.get("policy", "if-missing"))
        dockerfile = build_config["dockerfile"]
        context = build_config.get("context") or dockerfile.parent
        image_built_at = self.get_image_built_at(image)
        if not self.should_build(policy, image_built_at):
            return False
        try:
            self.run_build(
                image=image,
                dockerfile=dockerfile,
                context=context,
                build_args=build_args,
                refresh=policy.refreshes,
            )
        except subprocess.CalledProcessError:
            if not policy.refreshes or image_built_at is None:
                raise
            logger.warning(
                "Image refresh failed; running the existing %s instead", image
            )
            return False
        return True
