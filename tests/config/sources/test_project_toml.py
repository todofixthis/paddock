from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.project_toml import ProjectTomlSource


def _ctx(tmp_path) -> ConfigContext:
    parsed = ParsedArgs(
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
    return ConfigContext(
        parsed=parsed,
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )


def test_source_key():
    """SOURCE_KEY is 'project_toml'."""
    assert ProjectTomlSource.SOURCE_KEY == "project_toml"


def test_weight():
    """WEIGHT is 10."""
    assert ProjectTomlSource.WEIGHT == 10


def test_load_missing_returns_empty(tmp_path: Path):
    """Missing .paddock/config.toml yields a valid empty runner."""
    runner = ProjectTomlSource().load(_ctx(tmp_path))
    assert runner.is_valid()
    assert runner.cleaned_data == {}


def test_load_returns_validated_config(tmp_path: Path):
    """Valid .paddock/config.toml is loaded and validated."""
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "config.toml").write_text('image = "p:2"\nagent = "claude"\n')
    runner = ProjectTomlSource().load(_ctx(tmp_path))
    assert runner.is_valid()
    assert runner.cleaned_data == {"image": "p:2", "agent": "claude"}


def test_load_invalid_toml(tmp_path: Path):
    """Invalid TOML yields a non-valid runner."""
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "config.toml").write_text("not = valid = toml")
    runner = ProjectTomlSource().load(_ctx(tmp_path))
    assert not runner.is_valid()
