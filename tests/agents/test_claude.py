from pathlib import Path

from paddock.agents.claude import ClaudeAgent
from paddock.config.filters import VolumeSpec


def test_get_volumes_mounts_claude_json_when_present(tmp_path: Path) -> None:
    (tmp_path / ".claude.json").write_text("{}")

    volumes = ClaudeAgent().get_volumes()

    assert volumes[str(tmp_path / ".claude.json")] == VolumeSpec(
        "/root/.claude.json", "rw"
    )


def test_get_volumes_skips_claude_json_when_absent(tmp_path: Path) -> None:
    # Docker's -v creates a missing source path as a directory, which would
    # leave a directory where the host's Claude Code expects its config file.
    volumes = ClaudeAgent().get_volumes()

    assert str(tmp_path / ".claude.json") not in volumes


def test_get_volumes_skips_claude_json_when_not_a_file(tmp_path: Path) -> None:
    # Guards against widening is_file() to exists(): a directory is not a
    # config file Claude Code can read.
    (tmp_path / ".claude.json").mkdir()

    volumes = ClaudeAgent().get_volumes()

    assert str(tmp_path / ".claude.json") not in volumes


def test_get_volumes_always_mounts_claude_dir(tmp_path: Path) -> None:
    volumes = ClaudeAgent().get_volumes()

    assert volumes[str(tmp_path / ".claude")] == VolumeSpec("/root/.claude", "rw")
