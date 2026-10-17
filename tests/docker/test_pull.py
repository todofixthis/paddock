import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from paddock.docker.pull import ImagePuller, PullLog
from paddock.docker.source import BuildPolicy

IMAGE = "ghcr.io/example/agent:python"


def _stub_docker(mocker, *, present: bool, pull_returncode: int = 0):
    """Stub ``subprocess.run`` for ``docker image inspect`` and ``docker pull``.

    Args:
        mocker: pytest-mock fixture.
        present: Whether ``docker image inspect`` finds the image.
        pull_returncode: The stubbed ``docker pull``'s exit status.

    Returns:
        The ``subprocess.run`` mock.
    """

    def fake_run(argv, **kwargs):
        if argv[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(argv, 0 if present else 1)
        if pull_returncode and kwargs.get("check"):
            raise subprocess.CalledProcessError(pull_returncode, argv)
        return subprocess.CompletedProcess(argv, pull_returncode)

    return mocker.patch("paddock.docker.pull.subprocess.run", side_effect=fake_run)


def _pulled(mock_run) -> bool:
    """Whether the stubbed ``subprocess.run`` saw a ``docker pull``."""
    return any(c.args[0][:2] == ["docker", "pull"] for c in mock_run.call_args_list)


def _log(tmp_path: Path, pulled_ago: timedelta | None = None) -> PullLog:
    """A ``PullLog`` under ``tmp_path``, recording ``IMAGE`` if asked.

    Args:
        tmp_path: pytest's temp directory.
        pulled_ago: How long ago ``IMAGE`` was last pulled, or ``None`` for
            no record.

    Returns:
        The log.
    """
    log = PullLog(tmp_path / "state" / "pulls.json")
    if pulled_ago is not None:
        log.record(IMAGE, datetime.now(timezone.utc) - pulled_ago)
    return log


def test_default_path_uses_xdg_state_home(tmp_path):
    path = PullLog.default_path({"XDG_STATE_HOME": str(tmp_path)})
    assert path == tmp_path / "paddock" / "pulls.json"


@pytest.mark.parametrize("value", ["", "relative/state"])
def test_default_path_falls_back_to_local_state(value):
    path = PullLog.default_path({"XDG_STATE_HOME": value})
    assert path == Path.home() / ".local" / "state" / "paddock" / "pulls.json"


def test_log_round_trips_a_pull_time(tmp_path):
    pulled_at = datetime(2026, 10, 16, 9, 30, tzinfo=timezone.utc)
    log = _log(tmp_path)
    log.record(IMAGE, pulled_at)
    assert PullLog(log.path).last_pulled_at(IMAGE) == pulled_at


def test_log_keeps_other_images(tmp_path):
    log = _log(tmp_path, pulled_ago=timedelta(hours=1))
    log.record("other:latest", datetime.now(timezone.utc))
    assert log.last_pulled_at(IMAGE) is not None


def test_log_without_file_has_no_record(tmp_path):
    assert _log(tmp_path).last_pulled_at(IMAGE) is None


@pytest.mark.parametrize(
    "contents", ["not json", "[]", '{"ghcr.io/example/agent:python": "soon"}']
)
def test_log_treats_corrupt_file_as_empty(tmp_path, contents):
    log = _log(tmp_path)
    log.path.parent.mkdir(parents=True)
    log.path.write_text(contents)
    assert log.last_pulled_at(IMAGE) is None
    log.record(IMAGE, datetime.now(timezone.utc))
    assert log.last_pulled_at(IMAGE) is not None


def test_refresh_daily_pulls_stale_image(mocker, tmp_path, caplog):
    caplog.set_level("INFO", logger="paddock")
    mock_run = _stub_docker(mocker, present=True)
    log = _log(tmp_path, pulled_ago=timedelta(hours=25))
    assert ImagePuller(policy=BuildPolicy.DAILY, log=log).refresh(IMAGE)
    assert _pulled(mock_run)
    assert f"Pulling {IMAGE} (build.policy = daily)" in caplog.text
    pulled_at = log.last_pulled_at(IMAGE)
    assert pulled_at is not None
    assert datetime.now(timezone.utc) - pulled_at < timedelta(minutes=1)


def test_refresh_daily_skips_fresh_image(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=True)
    log = _log(tmp_path, pulled_ago=timedelta(hours=1))
    assert not ImagePuller(policy=BuildPolicy.DAILY, log=log).refresh(IMAGE)
    assert not _pulled(mock_run)


def test_refresh_weekly_skips_image_pulled_days_ago(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=True)
    log = _log(tmp_path, pulled_ago=timedelta(days=3))
    assert not ImagePuller(policy=BuildPolicy.WEEKLY, log=log).refresh(IMAGE)
    assert not _pulled(mock_run)


def test_refresh_daily_pulls_image_paddock_never_pulled(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=True)
    assert ImagePuller(policy=BuildPolicy.DAILY, log=_log(tmp_path)).refresh(IMAGE)
    assert _pulled(mock_run)


def test_refresh_pulls_missing_image_despite_fresh_record(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=False)
    log = _log(tmp_path, pulled_ago=timedelta(hours=1))
    assert ImagePuller(policy=BuildPolicy.DAILY, log=log).refresh(IMAGE)
    assert _pulled(mock_run)


def test_refresh_always_pulls_fresh_image(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=True)
    log = _log(tmp_path, pulled_ago=timedelta(minutes=1))
    assert ImagePuller(policy=BuildPolicy.ALWAYS, log=log).refresh(IMAGE)
    assert _pulled(mock_run)


def test_refresh_if_missing_skips_present_image(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=True)
    assert not ImagePuller(policy=BuildPolicy.IF_MISSING, log=_log(tmp_path)).refresh(
        IMAGE
    )
    assert not _pulled(mock_run)


def test_refresh_if_missing_pulls_absent_image(mocker, tmp_path):
    mock_run = _stub_docker(mocker, present=False)
    assert ImagePuller(policy=BuildPolicy.IF_MISSING, log=_log(tmp_path)).refresh(IMAGE)
    assert _pulled(mock_run)


def test_failed_pull_raises_and_leaves_record(mocker, tmp_path):
    _stub_docker(mocker, present=True, pull_returncode=1)
    log = _log(tmp_path, pulled_ago=timedelta(hours=25))
    before = log.last_pulled_at(IMAGE)
    with pytest.raises(subprocess.CalledProcessError):
        ImagePuller(policy=BuildPolicy.DAILY, log=log).refresh(IMAGE)
    assert log.last_pulled_at(IMAGE) == before


def test_unwritable_log_warns_after_pull(mocker, tmp_path, caplog):
    _stub_docker(mocker, present=True)
    blocker = tmp_path / "state"
    blocker.write_text("a file where the log's directory should be")
    log = PullLog(blocker / "pulls.json")
    assert ImagePuller(policy=BuildPolicy.DAILY, log=log).refresh(IMAGE)
    assert "Couldn't record the pull" in caplog.text
