from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.project_overrides import ProjectOverridesSource


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
    """SOURCE_KEY is 'project_overrides'."""
    assert ProjectOverridesSource.SOURCE_KEY == "project_overrides"


def test_weight():
    """WEIGHT is 30."""
    assert ProjectOverridesSource.WEIGHT == 30


def test_extracts_project_section(tmp_path: Path):
    """Returns the per-project config for the matching workdir."""
    cfg = tmp_path / "user.toml"
    cfg.write_text(
        'image = "u:1.0"\nagent = "claude"\n'
        f'[projects."{tmp_path.resolve()}"]\nimage = "p:2"\n'
    )
    result = ProjectOverridesSource().load(_ctx(tmp_path, cfg))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {"image": "p:2"}


def test_no_match_returns_empty(tmp_path: Path):
    """Returns an empty valid instance when the project key is absent."""
    cfg = tmp_path / "user.toml"
    cfg.write_text('image = "u:1.0"\nagent = "claude"\n')
    result = ProjectOverridesSource().load(_ctx(tmp_path, cfg))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_missing_file(tmp_path: Path):
    """Returns an empty valid instance when the config file is absent."""
    result = ProjectOverridesSource().load(_ctx(tmp_path, tmp_path / "nope.toml"))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_project_can_include_config_section(tmp_path: Path):
    """Per-project config.allowlist is preserved as meta, not in the instance."""
    cfg = tmp_path / "user.toml"
    cfg.write_text(
        'agent = "claude"\nimage = "u:1"\n'
        f'[projects."{tmp_path.resolve()}".config.allowlist]\nproject_toml = true\n'
    )
    result = ProjectOverridesSource().load(_ctx(tmp_path, cfg))
    assert result.instance.is_valid()
    assert "config" not in result.instance.cleaned_data
    assert result.meta["allowlist"]["project_toml"] is True
