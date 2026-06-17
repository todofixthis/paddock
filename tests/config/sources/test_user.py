from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.user import UserConfigSource


def _ctx(tmp_path, user_path) -> ConfigContext:
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
        user_config_path=user_path,
    )


def test_source_key():
    """SOURCE_KEY is 'user'."""
    assert UserConfigSource.SOURCE_KEY == "user"


def test_weight():
    """WEIGHT is 20."""
    assert UserConfigSource.WEIGHT == 20


def test_load_missing_returns_empty_runner(tmp_path: Path):
    """Missing config file yields a valid empty runner."""
    ctx = _ctx(tmp_path, tmp_path / "nope.toml")
    runner = UserConfigSource().load(ctx)
    assert runner.is_valid()
    assert runner.cleaned_data == {}


def test_load_strips_projects_and_config(tmp_path: Path):
    """projects and config sections are stripped; only standard keys remain."""
    cfg = tmp_path / "user.toml"
    cfg.write_text(
        'image = "u:1.0"\nagent = "claude"\n'
        '[projects."/abs"]\nimage = "p:2"\n'
        "[config.allowlist]\nproject_toml = true\n"
    )
    runner = UserConfigSource().load(_ctx(tmp_path, cfg))
    assert runner.is_valid()
    assert runner.cleaned_data == {"image": "u:1.0", "agent": "claude"}


def test_load_invalid_toml(tmp_path: Path):
    """Invalid TOML yields a non-valid runner."""
    cfg = tmp_path / "user.toml"
    cfg.write_text("not = valid = toml")
    runner = UserConfigSource().load(_ctx(tmp_path, cfg))
    assert not runner.is_valid()
