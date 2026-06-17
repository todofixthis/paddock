import logging
from pathlib import Path

import pytest

from paddock.config.errors import ConfigError
from paddock.config.project_dir import ProjectDirManager


def test_prepare_creates_missing_directory(tmp_path: Path):
    _, _, created = ProjectDirManager().prepare(tmp_path, readonly=True)
    assert (tmp_path / ".paddock").is_dir()
    assert created is True


def test_prepare_host_path_and_container_path_match(tmp_path: Path):
    host, spec, _ = ProjectDirManager().prepare(tmp_path, readonly=True)
    assert host == str(tmp_path / ".paddock")
    assert spec.container_path == host


def test_prepare_mode_ro(tmp_path: Path):
    _, spec, _ = ProjectDirManager().prepare(tmp_path, readonly=True)
    assert spec.mode == "ro"


def test_prepare_mode_rw(tmp_path: Path):
    _, spec, _ = ProjectDirManager().prepare(tmp_path, readonly=False)
    assert spec.mode == "rw"


def test_prepare_existing_not_marked_created(tmp_path: Path):
    (tmp_path / ".paddock").mkdir()
    _, _, created = ProjectDirManager().prepare(tmp_path, readonly=True)
    assert created is False


def test_prepare_paddock_is_file_raises(tmp_path: Path):
    (tmp_path / ".paddock").write_text("oops")
    with pytest.raises(ConfigError):
        ProjectDirManager().prepare(tmp_path, readonly=True)


def test_cleanup_removes_empty_when_created(tmp_path: Path):
    (tmp_path / ".paddock").mkdir()
    ProjectDirManager().cleanup(tmp_path, created_by_paddock=True)
    assert not (tmp_path / ".paddock").exists()


def test_cleanup_keeps_when_not_created(tmp_path: Path):
    (tmp_path / ".paddock").mkdir()
    ProjectDirManager().cleanup(tmp_path, created_by_paddock=False)
    assert (tmp_path / ".paddock").exists()


def test_cleanup_nonempty_warns(tmp_path: Path, caplog):
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "leftover").write_text("oops")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ProjectDirManager().cleanup(tmp_path, created_by_paddock=True)
    assert d.exists()
    assert any("contents" in r.message.lower() for r in caplog.records)


def test_cleanup_silent_when_absent(tmp_path: Path):
    ProjectDirManager().cleanup(tmp_path, created_by_paddock=True)
