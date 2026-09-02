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
