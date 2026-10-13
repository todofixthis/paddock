import json
import logging
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from paddock.docker.build import REFRESHED_AT_LABEL, BuildPolicy, ImageBuilder


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


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (BuildPolicy.ALWAYS, False),
        (BuildPolicy.DAILY, True),
        (BuildPolicy.IF_MISSING, False),
        (BuildPolicy.WEEKLY, True),
    ],
)
def test_policy_refreshes(policy, expected):
    assert policy.refreshes is expected


def test_run_build_uses_cache_by_default(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args={},
    )
    call_args = mock_run.call_args[0][0]
    assert "--no-cache" not in call_args
    assert "--pull" not in call_args
    assert "--label" not in call_args


def test_run_build_refresh_skips_cache_and_pulls(mocker):
    mock_run = mocker.patch("paddock.docker.build.subprocess.run")
    ImageBuilder().run_build(
        image="myapp:latest",
        dockerfile=Path("/path/Dockerfile"),
        context=Path("/path"),
        build_args={},
        refresh=True,
    )
    call_args = mock_run.call_args[0][0]
    assert "--no-cache" in call_args
    assert "--pull" in call_args
    label = call_args[call_args.index("--label") + 1]
    assert label.startswith(f"{REFRESHED_AT_LABEL}=")
    assert call_args[-1] == Path("/path")


def _maybe_build(
    mocker,
    policy: str,
    built_at: datetime | None,
    build_error: Exception | None = None,
):
    """Run ``maybe_build`` with docker stubbed out.

    Args:
        mocker: pytest-mock fixture.
        policy: Build policy value.
        built_at: The build time the stubbed inspect reports, or None for a
            missing image.
        build_error: Exception the stubbed ``run_build`` raises, if any.

    Returns:
        Tuple of ``maybe_build``'s return value and the ``run_build`` mock.
    """
    mocker.patch.object(ImageBuilder, "get_image_built_at", return_value=built_at)
    run_build = mocker.patch.object(ImageBuilder, "run_build", side_effect=build_error)
    built = ImageBuilder().maybe_build(
        build_config={"dockerfile": Path("/path/Dockerfile"), "policy": policy},
        image="myapp:latest",
        build_args={},
    )
    return built, run_build


def _build_failure() -> subprocess.CalledProcessError:
    """Return the error a failed ``docker build`` raises."""
    return subprocess.CalledProcessError(1, ["docker", "build"])


def test_maybe_build_periodic_refreshes(mocker):
    stale = datetime.now(timezone.utc) - timedelta(days=2)
    built, run_build = _maybe_build(mocker, "daily", stale)
    assert built
    assert run_build.call_args.kwargs["refresh"] is True


def test_maybe_build_always_keeps_cache(mocker):
    built, run_build = _maybe_build(mocker, "always", datetime.now(timezone.utc))
    assert built
    assert run_build.call_args.kwargs["refresh"] is False


def test_maybe_build_failed_refresh_keeps_existing_image(mocker, caplog):
    stale = datetime.now(timezone.utc) - timedelta(days=8)
    with caplog.at_level(logging.WARNING):
        built, _ = _maybe_build(mocker, "weekly", stale, _build_failure())
    assert not built
    assert "Image refresh failed" in caplog.text
    assert "myapp:latest" in caplog.text


def test_maybe_build_failed_refresh_without_image_raises(mocker):
    with pytest.raises(subprocess.CalledProcessError):
        _maybe_build(mocker, "daily", None, _build_failure())


def test_maybe_build_failed_cached_build_raises(mocker):
    with pytest.raises(subprocess.CalledProcessError):
        _maybe_build(mocker, "always", datetime.now(timezone.utc), _build_failure())


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


def test_get_image_built_at_prefers_refresh_label(mocker):
    built_at = _inspect(
        mocker,
        json.dumps(
            {
                "Config": {"Labels": {REFRESHED_AT_LABEL: "2026-10-13T22:30:00+00:00"}},
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
                "Config": {"Labels": {REFRESHED_AT_LABEL: "soon"}},
                "Created": "2026-10-10T02:18:25Z",
            }
        ),
    )
    assert built_at == datetime(2026, 10, 10, 2, 18, 25, tzinfo=timezone.utc)


def test_get_image_built_at_missing_image(mocker):
    assert _inspect(mocker, "", returncode=1) is None
