import logging
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


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    return path


def test_default_user_config_path_falls_back_to_legacy_with_warning(
    caplog, monkeypatch, tmp_path: Path
):
    """With XDG_CONFIG_HOME set but no config there, an existing
    ~/.config/paddock/config.toml is used, with a deprecation warning."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    legacy = _write_config(tmp_path / "home" / ".config" / "paddock" / "config.toml")
    xdg = tmp_path / "xdg"
    with caplog.at_level(logging.WARNING, logger="paddock"):
        path = ConfigContext.default_user_config_path({"XDG_CONFIG_HOME": str(xdg)})
    assert path == legacy
    assert [rec.message for rec in caplog.records] == [
        f"Reading user config from {legacy} because XDG_CONFIG_HOME is set and "
        f"{xdg / 'paddock' / 'config.toml'} does not exist. This fallback is "
        "deprecated and will be removed in paddock 2.0; move the file to "
        f"{xdg / 'paddock' / 'config.toml'}."
    ]


def test_default_user_config_path_prefers_xdg_and_warns_about_legacy(
    caplog, monkeypatch, tmp_path: Path
):
    """With config at both locations, the XDG one wins and the ignored
    ~/.config/paddock/config.toml is reported."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    legacy = _write_config(tmp_path / "home" / ".config" / "paddock" / "config.toml")
    xdg_config = _write_config(tmp_path / "xdg" / "paddock" / "config.toml")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        path = ConfigContext.default_user_config_path(
            {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}
        )
    assert path == xdg_config
    assert [rec.message for rec in caplog.records] == [
        f"Ignoring {legacy} because XDG_CONFIG_HOME is set; reading user config "
        f"from {xdg_config}. Remove {legacy}, merging anything it still needs "
        "into the XDG file."
    ]


def test_default_user_config_path_uses_xdg_silently_without_legacy(
    caplog, monkeypatch, tmp_path: Path
):
    """With config only at the XDG location, nothing is logged."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    xdg_config = _write_config(tmp_path / "xdg" / "paddock" / "config.toml")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        path = ConfigContext.default_user_config_path(
            {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}
        )
    assert path == xdg_config
    assert caplog.records == []


def test_default_user_config_path_silent_when_xdg_is_home_config(
    caplog, monkeypatch, tmp_path: Path
):
    """XDG_CONFIG_HOME=$HOME/.config names the legacy file itself, so there is
    nothing to warn about."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    legacy = _write_config(home / ".config" / "paddock" / "config.toml")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        path = ConfigContext.default_user_config_path(
            {"XDG_CONFIG_HOME": str(home / ".config")}
        )
    assert path == legacy
    assert caplog.records == []


def test_default_user_config_path_silent_when_xdg_symlinks_to_home_config(
    caplog, monkeypatch, tmp_path: Path
):
    """An XDG_CONFIG_HOME reaching ~/.config through a symlink names the same
    file, so there is nothing to warn about."""
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    legacy = _write_config(home / ".config" / "paddock" / "config.toml")
    link = tmp_path / "xdg-link"
    link.symlink_to(home / ".config")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        path = ConfigContext.default_user_config_path({"XDG_CONFIG_HOME": str(link)})
    assert path.samefile(legacy)
    assert caplog.records == []
