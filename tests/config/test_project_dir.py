import logging
from pathlib import Path

import pytest

from paddock.config.errors import PaddockEnvironmentError
from paddock.config.project_dir import ProjectDirManager


def test_not_a_directory_raises_environment_error(tmp_path):
    (tmp_path / ".paddock").write_text("oops")
    with pytest.raises(PaddockEnvironmentError):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass


def test_disabled_yields_none_and_no_dir(tmp_path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=False) as vol:
        assert vol is None
    assert not (tmp_path / ".paddock").exists()


def test_created_dir_removed_when_empty(tmp_path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=True) as vol:
        assert vol is not None
    assert not (tmp_path / ".paddock").exists()


def test_enter_host_path_and_container_path_match(tmp_path: Path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=True) as vol:
        assert vol is not None
        host, spec = vol
        assert host == str(tmp_path / ".paddock")
        assert spec.container_path == host


def test_enter_mode_ro(tmp_path: Path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=True) as vol:
        assert vol is not None
        assert vol[1].mode == "ro"


def test_enter_mode_rw(tmp_path: Path):
    with ProjectDirManager(tmp_path, readonly=False, enabled=True) as vol:
        assert vol is not None
        assert vol[1].mode == "rw"


def test_enter_existing_directory_left_in_place_after_exit(tmp_path: Path):
    (tmp_path / ".paddock").mkdir()
    with ProjectDirManager(tmp_path, readonly=True, enabled=True) as vol:
        assert vol is not None
    assert (tmp_path / ".paddock").exists()


def test_exit_nonempty_created_dir_warns_and_keeps(tmp_path: Path, caplog):
    with caplog.at_level(logging.WARNING, logger="paddock"):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            (tmp_path / ".paddock" / "leftover").write_text("oops")
    d = tmp_path / ".paddock"
    assert d.exists()
    assert any("contents" in r.message.lower() for r in caplog.records)


def test_exit_silent_when_dir_removed_inside_context(tmp_path: Path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=True):
        (tmp_path / ".paddock").rmdir()
    assert not (tmp_path / ".paddock").exists()


def test_symlink_to_directory_raises_and_is_left_untouched(tmp_path: Path):
    target = tmp_path / "elsewhere"
    target.mkdir()
    link = tmp_path / ".paddock"
    link.symlink_to(target)
    with pytest.raises(
        PaddockEnvironmentError, match="is a symlink; paddock will not mount"
    ):
        with ProjectDirManager(tmp_path, readonly=False, enabled=True):
            pass
    assert link.is_symlink()
    assert link.readlink() == target


def test_symlink_to_file_raises_and_is_left_untouched(tmp_path: Path):
    target = tmp_path / "secret.txt"
    target.write_text("secret")
    link = tmp_path / ".paddock"
    link.symlink_to(target)
    with pytest.raises(
        PaddockEnvironmentError, match="is a symlink; paddock will not mount"
    ):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert link.is_symlink()
    assert target.read_text() == "secret"


def test_dangling_symlink_raises_and_is_left_untouched(tmp_path: Path):
    link = tmp_path / ".paddock"
    link.symlink_to(tmp_path / "gone")
    with pytest.raises(
        PaddockEnvironmentError, match="is a symlink; paddock will not mount"
    ):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert link.is_symlink()


def test_disabled_ignores_a_symlinked_project_dir(tmp_path: Path):
    """The symlink check sits inside the ``enabled`` guard."""
    link = tmp_path / ".paddock"
    link.symlink_to(tmp_path)
    with ProjectDirManager(tmp_path, readonly=True, enabled=False) as vol:
        assert vol is None


def _flaky_rmdir(mocker, error: OSError, failures: int):
    """Patch ``Path.rmdir`` to raise ``error`` ``failures`` times, then succeed.

    Args:
        mocker: The pytest-mock fixture.
        error: The exception each failing call raises.
        failures: How many calls raise before the real ``rmdir`` runs.

    Returns:
        The autospec mock standing in for ``Path.rmdir``.
    """
    real_rmdir = Path.rmdir
    remaining = [failures]

    def fake(self: Path) -> None:
        if remaining[0] > 0:
            remaining[0] -= 1
            raise error
        real_rmdir(self)

    return mocker.patch.object(Path, "rmdir", autospec=True, side_effect=fake)


def test_exit_retries_transient_permission_error(tmp_path: Path, mocker):
    sleep = mocker.patch("paddock.config.project_dir.sleep")
    rmdir = _flaky_rmdir(mocker, PermissionError(13, "denied"), failures=1)
    with ProjectDirManager(tmp_path, readonly=True, enabled=True):
        pass
    assert not (tmp_path / ".paddock").exists()
    assert rmdir.call_count == 2
    sleep.assert_called_once_with(0.1)


def test_exit_persistent_permission_error_warns_and_keeps(
    tmp_path: Path, mocker, caplog
):
    sleep = mocker.patch("paddock.config.project_dir.sleep")
    rmdir = _flaky_rmdir(mocker, PermissionError(13, "denied"), failures=10)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert (tmp_path / ".paddock").is_dir()
    assert rmdir.call_count == 10
    # No sleep after the last attempt.
    assert sleep.call_count == 9
    assert any(str(tmp_path / ".paddock") in r.getMessage() for r in caplog.records)


def test_exit_other_os_error_from_rmdir_warns_without_retry(
    tmp_path: Path, mocker, caplog
):
    sleep = mocker.patch("paddock.config.project_dir.sleep")
    rmdir = _flaky_rmdir(mocker, OSError(16, "busy"), failures=1)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert (tmp_path / ".paddock").is_dir()
    assert rmdir.call_count == 1
    sleep.assert_not_called()
    assert any(str(tmp_path / ".paddock") in r.getMessage() for r in caplog.records)


def test_exit_rmdir_file_not_found_is_silent(tmp_path: Path, mocker, caplog):
    mocker.patch("paddock.config.project_dir.sleep")
    rmdir = _flaky_rmdir(mocker, FileNotFoundError(2, "gone"), failures=1)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert rmdir.call_count == 1
    assert not caplog.records


def test_exit_iterdir_permission_error_warns(tmp_path: Path, mocker, caplog):
    mocker.patch.object(
        Path, "iterdir", autospec=True, side_effect=PermissionError(13, "denied")
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass
    assert (tmp_path / ".paddock").is_dir()
    assert any(str(tmp_path / ".paddock") in r.getMessage() for r in caplog.records)
