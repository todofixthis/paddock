from pathlib import Path
from typing import Any

import pytest

from paddock.config.errors import ConfigError
from paddock.config.filters import VolumeSpec
from paddock.config.server_settings import ServerSettings


def _settings(
    config: dict[str, Any], default_image: str | None = None
) -> ServerSettings:
    """Check ``config`` as server ``srv``'s merged settings table."""
    return ServerSettings.from_config(config, key="srv", default_image=default_image)


def _messages(config: dict[str, Any], default_image: str | None = None) -> list[str]:
    """Return the message of every error ``config`` raises."""
    with pytest.raises(ExceptionGroup) as exc:
        _settings(config, default_image)
    assert all(isinstance(e, ConfigError) for e in exc.value.exceptions)
    return [str(e) for e in exc.value.exceptions]


def test_settings_resolve_volumes_and_image(tmp_path: Path) -> None:
    """A volume is keyed by its resolved host path; unset settings are None."""
    d = tmp_path / "d"
    d.mkdir()
    settings = _settings(
        {"image": "img", "volumes": {str(d): VolumeSpec(str(d), "rw")}}
    )
    assert settings.image == "img"
    assert settings.volumes == {str(d.resolve()): VolumeSpec(str(d), "rw")}
    assert settings.build is None
    assert settings.port is None


def test_a_volume_may_be_a_file(tmp_path: Path) -> None:
    """A file is as good a host path as a directory."""
    file = tmp_path / "f.txt"
    file.write_text("x")
    settings = _settings({"image": "i", "volumes": {str(file): VolumeSpec("/f", "ro")}})
    assert settings.volumes == {str(file.resolve()): VolumeSpec("/f", "ro")}


def test_default_image_fills_a_missing_image() -> None:
    assert _settings({}, default_image="base").image == "base"


def test_configured_image_beats_the_default() -> None:
    assert _settings({"image": "mine"}, default_image="base").image == "mine"


def test_missing_image_without_a_default_is_an_error() -> None:
    assert _messages({}) == [
        '[agents.srv.server.image] No image is set, and server "srv" has no default'
    ]


def test_missing_volume_path_is_an_error() -> None:
    messages = _messages(
        {"image": "i", "volumes": {"/no/such": VolumeSpec("/x", "ro")}}
    )
    assert len(messages) == 1
    assert messages[0].startswith("[agents.srv.server.volumes./no/such] ")


def test_tilde_volume_is_expanded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A leading ``~`` is the user's home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "Dev").mkdir()
    settings = _settings({"image": "i", "volumes": {"~/Dev": VolumeSpec("/dev", "rw")}})
    assert list(settings.volumes) == [str((tmp_path / "Dev").resolve())]


def test_a_missing_dockerfile_is_an_error(tmp_path: Path) -> None:
    messages = _messages({"image": "i", "build": {"dockerfile": str(tmp_path / "no")}})
    assert len(messages) == 1
    assert messages[0].startswith("[agents.srv.server.build.dockerfile] ")


def test_a_missing_context_is_an_error(tmp_path: Path) -> None:
    messages = _messages({"image": "i", "build": {"context": str(tmp_path / "no")}})
    assert len(messages) == 1
    assert messages[0].startswith("[agents.srv.server.build.context] ")


def test_build_defaults_match_the_top_level_build(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM scratch\n")
    settings = _settings({"image": "i", "build": {"dockerfile": str(dockerfile)}})
    assert settings.build == {
        "args": {},
        "context": None,
        "dockerfile": dockerfile.resolve(),
        "policy": "if-missing",
    }


def test_build_without_a_dockerfile_is_kept() -> None:
    """A policy alone pulls under that policy (ADR 013)."""
    settings = _settings({"image": "i", "build": {"policy": "daily"}})
    assert settings.build is not None
    assert settings.build["dockerfile"] is None
    assert settings.build["policy"] == "daily"


def test_port_is_carried() -> None:
    assert _settings({"image": "i", "port": 4096}).port == 4096


def test_every_problem_is_reported(tmp_path: Path) -> None:
    messages = _messages(
        {
            "image": "i",
            "build": {"dockerfile": str(tmp_path / "no")},
            "volumes": {"/no/such": VolumeSpec("/x", "ro")},
        }
    )
    assert len(messages) == 2
