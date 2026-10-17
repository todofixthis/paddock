import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from paddock.docker.build import BUILT_AT_LABEL, ImageBuilder
from paddock.docker.source import BuildPolicy


def _builder(
    policy: BuildPolicy = BuildPolicy.IF_MISSING, build_args: dict | None = None
) -> ImageBuilder:
    """An ``ImageBuilder`` for ``/path/Dockerfile`` with the given policy."""
    return ImageBuilder(
        policy=policy,
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args=build_args or {},
    )


def test_refresh_builds_when_due(mocker):
    mocker.patch.object(ImageBuilder, "get_image_built_at", return_value=None)
    mock_run_build = mocker.patch.object(ImageBuilder, "run_build")
    assert _builder().refresh("myapp:latest")
    mock_run_build.assert_called_once_with("myapp:latest")


def test_refresh_skips_fresh_image(mocker):
    mocker.patch.object(
        ImageBuilder, "get_image_built_at", return_value=datetime.now(timezone.utc)
    )
    mock_run_build = mocker.patch.object(ImageBuilder, "run_build")
    assert not _builder(BuildPolicy.DAILY).refresh("myapp:latest")
    mock_run_build.assert_not_called()


def test_run_build_basic(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    _builder(build_args={}).run_build("myapp:latest")
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[:3] == ["docker", "build", "-t"]
    assert "myapp:latest" in call_args
    assert "-f" in call_args


def test_run_build_with_args(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    _builder(build_args={"AGENT": "claude"}).run_build("myapp:latest")
    call_args = mock_run.call_args[0][0]
    assert "--build-arg" in call_args
    assert "AGENT=claude" in call_args


def test_run_build_stamps_build_time(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    before = datetime.now(timezone.utc)
    _builder(build_args={}).run_build("myapp:latest")
    call_args = mock_run.call_args[0][0]
    key, _, value = call_args[call_args.index("--label") + 1].partition("=")
    assert key == BUILT_AT_LABEL
    assert datetime.fromisoformat(value) >= before
    assert "--no-cache" not in call_args


def _inspect(mocker, stdout: str, returncode: int = 0) -> datetime | None:
    """Run ``get_image_built_at`` against a stubbed ``docker image inspect``.

    Args:
        mocker: pytest-mock fixture.
        stdout: What the stubbed inspect prints.
        returncode: The stubbed inspect's exit status.

    Returns:
        ``get_image_built_at``'s result.
    """
    mocker.patch(
        "paddock.docker.build.subprocess.run",
        return_value=subprocess.CompletedProcess([], returncode, stdout=stdout),
    )
    return ImageBuilder.get_image_built_at("myapp:latest")


def test_get_image_built_at_prefers_built_at_label(mocker):
    built_at = _inspect(
        mocker,
        json.dumps(
            {
                "Config": {"Labels": {BUILT_AT_LABEL: "2026-10-13T22:30:00+00:00"}},
                "Created": "1970-01-01T00:00:00Z",
            }
        ),
    )
    assert built_at == datetime(2026, 10, 13, 22, 30, tzinfo=timezone.utc)


def test_get_image_built_at_falls_back_to_created(mocker):
    built_at = _inspect(
        mocker,
        json.dumps(
            {"Config": {"Labels": None}, "Created": "2026-10-10T02:18:25.310286353Z"}
        ),
    )
    assert built_at is not None
    assert built_at.date() == datetime(2026, 10, 10).date()


def test_get_image_built_at_ignores_invalid_label(mocker):
    built_at = _inspect(
        mocker,
        json.dumps(
            {
                "Config": {"Labels": {BUILT_AT_LABEL: "soon"}},
                "Created": "2026-10-10T02:18:25Z",
            }
        ),
    )
    assert built_at == datetime(2026, 10, 10, 2, 18, 25, tzinfo=timezone.utc)


def test_get_image_built_at_missing_image(mocker):
    assert _inspect(mocker, "", returncode=1) is None


def test_get_image_built_at_treats_malformed_timestamps_as_missing(mocker):
    built_at = _inspect(
        mocker,
        json.dumps(
            {
                "Config": {"Labels": {BUILT_AT_LABEL: "soon"}},
                "Created": "yesterday",
            }
        ),
    )
    assert built_at is None
