from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext


def _empty_parsed() -> ParsedArgs:
    return ParsedArgs(
        agent=None,
        build_args={},
        build_context=None,
        build_dockerfile=None,
        build_policy=None,
        command=[],
        config_file=None,
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
