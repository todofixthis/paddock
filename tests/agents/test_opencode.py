from pathlib import Path

import pytest

from paddock.agents import agent_registry
from paddock.agents.opencode import OpenCodeAgent
from paddock.config.filters import VolumeSpec


def test_registry_resolves_opencode() -> None:
    assert isinstance(agent_registry["opencode"], OpenCodeAgent)


def test_get_volumes_mounts_default_xdg_dirs(tmp_path: Path) -> None:
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    (tmp_path / ".local" / "share" / "opencode").mkdir(parents=True)

    volumes = OpenCodeAgent().get_volumes()

    assert volumes == {
        str(tmp_path / ".config" / "opencode"): VolumeSpec(
            "/root/.config/opencode", "rw"
        ),
        str(tmp_path / ".local" / "share" / "opencode"): VolumeSpec(
            "/root/.local/share/opencode", "rw"
        ),
    }


def test_get_volumes_follows_host_xdg_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "cfg" / "opencode").mkdir(parents=True)
    (tmp_path / "data" / "opencode").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    volumes = OpenCodeAgent().get_volumes()

    # Container side stays at the XDG defaults: the container sets no XDG vars.
    assert volumes == {
        str(tmp_path / "cfg" / "opencode"): VolumeSpec("/root/.config/opencode", "rw"),
        str(tmp_path / "data" / "opencode"): VolumeSpec(
            "/root/.local/share/opencode", "rw"
        ),
    }


def test_get_volumes_treats_empty_xdg_var_as_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", "")

    volumes = OpenCodeAgent().get_volumes()

    assert str(tmp_path / ".config" / "opencode") in volumes


def test_get_volumes_skips_missing_dirs(tmp_path: Path) -> None:
    # Docker's -v creates a missing source path owned by root, locking the
    # host's OpenCode out of its own directory.
    assert OpenCodeAgent().get_volumes() == {}


def test_get_volumes_skips_dir_that_is_a_file(tmp_path: Path) -> None:
    # Guards against widening is_dir() to exists().
    (tmp_path / ".config").mkdir()
    (tmp_path / ".config" / "opencode").write_text("")

    assert OpenCodeAgent().get_volumes() == {}


def test_get_volumes_never_mounts_state_dir(tmp_path: Path) -> None:
    # The state dir registers the host's background service by an address
    # the container cannot reach.
    (tmp_path / ".local" / "state" / "opencode").mkdir(parents=True)

    assert OpenCodeAgent().get_volumes() == {}


def test_get_command_and_build_args() -> None:
    agent = OpenCodeAgent()

    assert agent.get_command() == ["opencode"]
    assert agent.get_build_args() == {"AGENT": "opencode"}
