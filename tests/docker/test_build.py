import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from paddock.docker.build import BUILT_AT_LABEL, BuildPolicy, ImageBuilder


def test_should_build_always():
    assert ImageBuilder.should_build(
        BuildPolicy.ALWAYS, image_built_at=datetime.now(timezone.utc)
    )


def test_should_build_if_missing_image_exists():
    assert not ImageBuilder.should_build(
        BuildPolicy.IF_MISSING, image_built_at=datetime.now(timezone.utc)
    )


def test_should_build_if_missing_image_absent():
    assert ImageBuilder.should_build(BuildPolicy.IF_MISSING, image_built_at=None)


def test_should_build_daily_old_image():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    assert ImageBuilder.should_build(BuildPolicy.DAILY, image_built_at=old)


def test_should_build_daily_fresh_image():
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not ImageBuilder.should_build(BuildPolicy.DAILY, image_built_at=fresh)


def test_should_build_weekly_old_image():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert ImageBuilder.should_build(BuildPolicy.WEEKLY, image_built_at=old)


def test_run_build_basic(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args={},
    )
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[:3] == ["docker", "build", "-t"]
    assert "myapp:latest" in call_args
    assert "-f" in call_args


def test_run_build_with_args(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args={"AGENT": "claude"},
    )
    call_args = mock_run.call_args[0][0]
    assert "--build-arg" in call_args
    assert "AGENT=claude" in call_args


def test_run_build_stamps_build_time(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    before = datetime.now(timezone.utc)
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args={},
    )
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
    return ImageBuilder().get_image_built_at("myapp:latest")


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
