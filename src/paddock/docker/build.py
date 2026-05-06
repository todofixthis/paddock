import subprocess
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import filters as f


class BuildPolicy(StrEnum):
    ALWAYS = "always"
    DAILY = "daily"
    IF_MISSING = "if-missing"
    WEEKLY = "weekly"


class ImageBuilder:
    @staticmethod
    def should_build(policy: BuildPolicy, image_created_at: datetime | None) -> bool:
        """Determine whether to build the image given the policy and current image age."""
        match policy:
            case BuildPolicy.ALWAYS:
                return True
            case BuildPolicy.IF_MISSING:
                return image_created_at is None
            case BuildPolicy.DAILY:
                if image_created_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_created_at) > timedelta(
                    hours=24
                )
            case BuildPolicy.WEEKLY:
                if image_created_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_created_at) > timedelta(
                    days=7
                )

    def get_image_created_at(self, image: str) -> datetime | None:
        """Return the creation timestamp of a local Docker image, or None if absent."""
        result = subprocess.run(
            ["docker", "image", "inspect", "--format={{.Created}}", image],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        created_str = result.stdout.strip()
        runner = f.FilterRunner(f.Datetime(), created_str)
        if not runner.is_valid():
            return None
        return runner.cleaned_data

    def run_build(
        self,
        *,
        image: str,
        dockerfile: str,
        context: str,
        build_args: dict[str, str],
    ) -> None:
        """Run docker build, streaming output to stdout."""
        argv = ["docker", "build", "-t", image, "-f", dockerfile]
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
        context = build_config.get("context") or str(Path(dockerfile).parent)
        image_created_at = self.get_image_created_at(image)
        if self.should_build(policy, image_created_at):
            self.run_build(
                image=image,
                dockerfile=dockerfile,
                context=context,
                build_args=build_args,
            )
            return True
        return False
