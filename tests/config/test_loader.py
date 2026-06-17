import logging
import os
from pathlib import Path

import filters as f
import pytest
from filters.pytest import skip_value_check

from paddock.cli import ParsedArgs
from paddock.config.errors import ConfigError
from paddock.config.loader import ConfigLoader, ResolvedConfig
from paddock.config.sources.env import _env_schema


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


def _setup_home(tmp_path, monkeypatch, contents: str) -> Path:
    home = tmp_path
    cfg = home / ".config" / "paddock" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(contents)
    monkeypatch.setenv("HOME", str(home))
    return cfg


def test_apply_defaults(tmp_path: Path):
    """Default values are set when not supplied by any config source."""
    loader = ConfigLoader()
    result = loader._apply_defaults({})
    assert result["agent"] == "claude"
    assert result["volumes"] == {}


def test_resolve_returns_config_dict(tmp_path: Path, monkeypatch):
    """resolve() returns a ResolvedConfig with the correct values."""
    _setup_home(tmp_path, monkeypatch, 'image = "ubuntu:22.04"\nagent = "claude"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert isinstance(r, ResolvedConfig)
    assert r.config["image"] == "ubuntu:22.04"


# ---------------------------------------------------------------------------
# _env_schema
# ---------------------------------------------------------------------------


def test_env_schema_expands_tilde_in_dockerfile(
    assert_filter_passes, monkeypatch, tmp_path
):
    """PADDOCK_BUILD_DOCKERFILE with a leading tilde is expanded by the env schema."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    runner = assert_filter_passes(
        _env_schema,
        {"PADDOCK_BUILD_DOCKERFILE": "~/Dockerfile"},
        skip_value_check,
    )
    assert runner.cleaned_data["PADDOCK_BUILD_DOCKERFILE"] == dockerfile.resolve()


def test_env_schema_rejects_empty_dockerfile(assert_filter_errors):
    """PADDOCK_BUILD_DOCKERFILE="" is rejected — empty string would silently resolve to CWD."""
    assert_filter_errors(
        _env_schema,
        {"PADDOCK_BUILD_DOCKERFILE": ""},
        {"PADDOCK_BUILD_DOCKERFILE": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_env_schema_rejects_empty_context(assert_filter_errors):
    """PADDOCK_BUILD_CONTEXT="" is rejected — empty string would silently resolve to CWD."""
    assert_filter_errors(
        _env_schema,
        {"PADDOCK_BUILD_CONTEXT": ""},
        {"PADDOCK_BUILD_CONTEXT": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_env_schema_rejects_invalid_policy(assert_filter_errors):
    """PADDOCK_BUILD_POLICY with an unrecognised value is invalid."""
    assert_filter_errors(
        _env_schema,
        {"PADDOCK_BUILD_POLICY": "never"},
        {"PADDOCK_BUILD_POLICY": [f.Choice.CODE_INVALID]},
        skip_value_check,
    )


def test_env_schema_ignores_non_paddock_vars(assert_filter_passes):
    """Non-PADDOCK_* vars in the env are silently ignored."""
    assert_filter_passes(
        _env_schema, {"PATH": "/usr/bin", "HOME": "/home/user"}, skip_value_check
    )


def test_env_build_args_not_mapped(tmp_path, monkeypatch):
    """PADDOCK_BUILD_ARGS is silently ignored — it cannot express a key=value dict as a single env var."""
    _setup_home(tmp_path, monkeypatch, 'image = "ubuntu:22.04"\nagent = "claude"\n')
    result = ConfigLoader().resolve(
        _empty_parsed(), workdir=tmp_path, environ={"PADDOCK_BUILD_ARGS": "FOO=bar"}
    )
    assert isinstance(result, ResolvedConfig)
    assert result.config.get("build") is None


def test_loader_resolve_env_dockerfile_tilde_expanded(monkeypatch, tmp_path):
    """A tilde in PADDOCK_BUILD_DOCKERFILE is expanded through ConfigLoader.resolve()."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    monkeypatch.setenv("PADDOCK_BUILD_DOCKERFILE", "~/Dockerfile")
    monkeypatch.setenv("PADDOCK_IMAGE", "myimage")
    monkeypatch.setenv("PADDOCK_AGENT", "claude")

    result = ConfigLoader().resolve(
        _empty_parsed(), workdir=tmp_path, environ=dict(os.environ)
    )
    assert isinstance(result, ResolvedConfig)
    assert result.config["build"]["dockerfile"] == dockerfile.resolve()


def test_resolve_raises_on_invalid_env(tmp_path: Path, monkeypatch):
    """resolve() raises ExceptionGroup when an env var fails validation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ExceptionGroup):
        ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_BUILD_POLICY": "never"},
        )


def test_resolve_raises_on_invalid_config(tmp_path: Path, monkeypatch):
    """resolve() raises ExceptionGroup when required config fields are missing."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # No image supplied from any source — required field must fail
    with pytest.raises(ExceptionGroup):
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})


# ---------------------------------------------------------------------------
# New tests — registry-driven four-phase workflow
# ---------------------------------------------------------------------------


def test_resolve_returns_resolved_config(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch, 'image = "u:1.0"\nagent = "claude"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert isinstance(r, ResolvedConfig)
    assert r.config["image"] == "u:1.0"


def test_project_toml_opt_in(tmp_path: Path, monkeypatch):
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\n[config.allowlist]\nproject_toml = true\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('image = "p:2.0"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "p:2.0"
    assert r.project_toml_enabled is True


def test_project_toml_blocked_by_default(tmp_path: Path, monkeypatch, caplog):
    _setup_home(tmp_path, monkeypatch, 'image = "u:1"\nagent = "claude"\n')
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('image = "blocked"\n')
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "u:1"
    assert r.project_toml_enabled is False
    assert any("ignored" in rec.message.lower() for rec in caplog.records)


def test_env_blocked_by_allowlist_warns(tmp_path: Path, monkeypatch, caplog):
    """Generic blocked-source behaviour applies to env too."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\nenv = false\n',
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_IMAGE": "ignored"},
        )
    assert r.config["image"] == "u"
    assert any(
        "env" in rec.message.lower() and "ignored" in rec.message.lower()
        for rec in caplog.records
    )


def test_invalid_env_blocked_source_downgraded_to_warning(
    tmp_path: Path, monkeypatch, caplog
):
    """A source disabled by the allowlist whose load is also invalid does not error."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\nenv = false\n',
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_BUILD_POLICY": "bogus"},
        )
    assert r.config["image"] == "u"


def test_project_overrides_beat_user_global(tmp_path: Path, monkeypatch):
    _setup_home(
        tmp_path,
        monkeypatch,
        f'image = "global"\nagent = "claude"\n'
        f'[projects."{tmp_path.resolve()}"]\nimage = "override"\n',
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "override"


def test_user_beats_project_toml(tmp_path: Path, monkeypatch):
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "user"\nagent = "claude"\n[config.allowlist]\nproject_toml = true\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('image = "project"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "user"


def test_per_project_allowlist_shadows_global(tmp_path: Path, monkeypatch):
    # User config has no image — project_toml is the only image source.
    # The global allowlist blocks project_toml, but the per-project allowlist
    # enables it; the per-project rule should win, so "p" should appear.
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\n'
        "[config.allowlist]\nproject_toml = false\n"
        f'[projects."{tmp_path.resolve()}".config.allowlist]\nproject_toml = true\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('image = "p"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "p"


def test_cli_beats_env_beats_user(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch, 'agent = "claude"\nimage = "user"\n')

    parsed = _empty_parsed()
    parsed.image = "cli"
    r = ConfigLoader().resolve(
        parsed, workdir=tmp_path, environ={"PADDOCK_IMAGE": "env"}
    )
    assert r.config["image"] == "cli"

    r2 = ConfigLoader().resolve(
        _empty_parsed(), workdir=tmp_path, environ={"PADDOCK_IMAGE": "env"}
    )
    assert r2.config["image"] == "env"


def test_env_allowlist_restricts_keys(tmp_path: Path, monkeypatch):
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\nenv = ["network"]\n',
    )
    r = ConfigLoader().resolve(
        _empty_parsed(),
        workdir=tmp_path,
        environ={"PADDOCK_IMAGE": "env-img", "PADDOCK_NETWORK": "mynet"},
    )
    assert r.config["image"] == "u"
    assert r.config["network"] == "mynet"


def test_invalid_source_raises_exception_group(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch, "not = valid = toml")
    with pytest.raises(ExceptionGroup) as exc_info:
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert all(isinstance(e, ConfigError) for e in exc_info.value.exceptions)


def test_multiple_invalid_sources_aggregated(tmp_path: Path, monkeypatch):
    """All invalid (non-blocked) sources surface together."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u:1"\n[config.allowlist]\nproject_toml = true\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text("not = valid = toml")
    with pytest.raises(ExceptionGroup) as exc_info:
        ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_BUILD_POLICY": "bogus"},
        )
    messages = " ".join(str(e) for e in exc_info.value.exceptions)
    assert "project_toml" in messages
    assert "env" in messages


def test_project_dir_readonly_default_true(tmp_path: Path, monkeypatch):
    _setup_home(tmp_path, monkeypatch, 'agent = "claude"\nimage = "u"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.project_dir_readonly is True


def test_project_dir_readonly_false(tmp_path: Path, monkeypatch):
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config]\nproject_dir_readonly = false\n',
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.project_dir_readonly is False
