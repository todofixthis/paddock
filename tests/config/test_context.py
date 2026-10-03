from pathlib import Path

import pytest

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext


def _empty_parsed() -> ParsedArgs:
    return ParsedArgs(
        agent=None,
        agent_args=[],
        build_args={},
        build_context=None,
        build_dockerfile=None,
        build_policy=None,
        command=[],
        dry_run=False,
        image=None,
        network=None,
        quiet=False,
        volumes={},
        workdir=None,
    )


def test_construction(tmp_path: Path):
    ctx = ConfigContext(
        parsed=_empty_parsed(),
        environ={"X": "1"},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )
    assert ctx.workdir == tmp_path
    assert ctx.environ == {"X": "1"}


def test_project_key_is_resolved_workdir(tmp_path: Path):
    """project_key is the resolved absolute path string of workdir."""
    ctx = ConfigContext(
        parsed=_empty_parsed(),
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )
    assert ctx.project_key == str(tmp_path.resolve())


def test_frozen(tmp_path: Path):
    import dataclasses
    import pytest

    ctx = ConfigContext(
        parsed=_empty_parsed(),
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.workdir = tmp_path / "other"  # type: ignore[misc]


def test_default_user_config_path_follows_home(monkeypatch, tmp_path: Path):
    """The default path is resolved per-call against the current $HOME."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (
        ConfigContext.default_user_config_path({})
        == tmp_path / ".config" / "paddock" / "config.toml"
    )


def test_default_user_config_path_follows_xdg_config_home(tmp_path: Path):
    """An absolute XDG_CONFIG_HOME replaces ~/.config as the base directory."""
    xdg = tmp_path / "xdg"
    assert (
        ConfigContext.default_user_config_path({"XDG_CONFIG_HOME": str(xdg)})
        == xdg / "paddock" / "config.toml"
    )


@pytest.mark.parametrize("xdg_config_home", ["", "relative/config"])
def test_default_user_config_path_ignores_invalid_xdg_config_home(
    monkeypatch, tmp_path: Path, xdg_config_home: str
):
    """An empty or relative XDG_CONFIG_HOME is invalid per the XDG spec, so the
    path falls back to ~/.config."""
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (
        ConfigContext.default_user_config_path({"XDG_CONFIG_HOME": xdg_config_home})
        == tmp_path / ".config" / "paddock" / "config.toml"
    )
