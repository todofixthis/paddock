import logging
import os
from pathlib import Path

import filters as f
import pytest
from filters.pytest import skip_value_check

from class_registry import ClassRegistry

from paddock.agents import BaseAgent
from paddock.agents.servers import BaseServer, ServerConnection
from paddock.cli import ParsedArgs
from paddock.config.agent_choice import UNNAMED_SERVER
from paddock.config.errors import ConfigError
from paddock.config.loader import ConfigLoader, ResolvedConfig
from paddock.config.sources.env import _env_schema


def _empty_parsed() -> ParsedArgs:
    return ParsedArgs(
        agent=None,
        agent_args=[],
        agent_client=None,
        agent_server=None,
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
    assert result["agent"] == {"client": "claude", "server": UNNAMED_SERVER}
    assert result["volumes"] == {}


def test_resolve_reads_user_config_from_xdg_config_home(tmp_path: Path):
    """resolve() loads the user config from $XDG_CONFIG_HOME/paddock when set."""
    xdg = tmp_path / "xdg"
    cfg = xdg / "paddock" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('image = "ubuntu:24.04"\n')
    r = ConfigLoader().resolve(
        _empty_parsed(), workdir=tmp_path, environ={"XDG_CONFIG_HOME": str(xdg)}
    )
    assert r.config["image"] == "ubuntu:24.04"


def test_resolve_falls_back_to_legacy_user_config(tmp_path: Path, monkeypatch):
    """resolve() still loads ~/.config/paddock/config.toml when XDG_CONFIG_HOME
    is set but holds no paddock config."""
    _setup_home(tmp_path, monkeypatch, 'image = "ubuntu:22.04"\n')
    r = ConfigLoader().resolve(
        _empty_parsed(),
        workdir=tmp_path,
        environ={"XDG_CONFIG_HOME": str(tmp_path / "xdg")},
    )
    assert r.config["image"] == "ubuntu:22.04"


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
        _env_schema(Path.cwd()),
        {"PADDOCK_BUILD_DOCKERFILE": "~/Dockerfile"},
        skip_value_check,
    )
    assert runner.cleaned_data["PADDOCK_BUILD_DOCKERFILE"] == dockerfile.resolve()


def test_env_schema_rejects_empty_dockerfile(assert_filter_errors):
    """PADDOCK_BUILD_DOCKERFILE="" is rejected — empty string would silently resolve to CWD."""
    assert_filter_errors(
        _env_schema(Path.cwd()),
        {"PADDOCK_BUILD_DOCKERFILE": ""},
        {"PADDOCK_BUILD_DOCKERFILE": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_env_schema_rejects_empty_context(assert_filter_errors):
    """PADDOCK_BUILD_CONTEXT="" is rejected — empty string would silently resolve to CWD."""
    assert_filter_errors(
        _env_schema(Path.cwd()),
        {"PADDOCK_BUILD_CONTEXT": ""},
        {"PADDOCK_BUILD_CONTEXT": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_env_schema_rejects_invalid_policy(assert_filter_errors):
    """PADDOCK_BUILD_POLICY with an unrecognised value is invalid."""
    assert_filter_errors(
        _env_schema(Path.cwd()),
        {"PADDOCK_BUILD_POLICY": "never"},
        {"PADDOCK_BUILD_POLICY": [f.Choice.CODE_INVALID]},
        skip_value_check,
    )


def test_env_build_args_suffixed_name_is_fatal(tmp_path, monkeypatch):
    """PADDOCK_BUILD_ARGS_<NAME> aborts the run, naming the variable."""
    _setup_home(tmp_path, monkeypatch, 'image = "ubuntu:22.04"\nagent = "claude"\n')
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM x")
    with pytest.raises(ExceptionGroup) as exc:
        ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={
                "PADDOCK_BUILD_ARGS_NODE_VERSION": "24",
                "PADDOCK_BUILD_DOCKERFILE": str(dockerfile),
            },
        )
    messages = [str(e) for e in exc.value.exceptions]
    assert messages == [
        "[env:PADDOCK_BUILD_ARGS_NODE_VERSION] Unexpected key "
        '"PADDOCK_BUILD_ARGS_NODE_VERSION".'
    ]


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
    warnings = [rec.message for rec in caplog.records]
    assert (
        "project_toml: dropped non-allowlisted keys image — add them to "
        "[config.allowlist].project_toml to keep them" in warnings
    )
    assert len(warnings) == 1


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
    warnings = [rec.message for rec in caplog.records]
    assert (
        "env: dropped non-allowlisted keys image — add them to "
        "[config.allowlist].env to keep them" in warnings
    )
    assert len(warnings) == 1


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


def test_env_allowlist_restricts_keys(tmp_path: Path, monkeypatch, caplog):
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\nenv = ["network"]\n',
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_IMAGE": "env-img", "PADDOCK_NETWORK": "mynet"},
        )
    assert r.config["image"] == "u"
    assert r.config["network"] == "mynet"
    warnings = [rec.message for rec in caplog.records]
    assert (
        "env: dropped non-allowlisted keys image — add them to "
        "[config.allowlist].env to keep them" in warnings
    )
    assert len(warnings) == 1


def test_cli_allowlist_restricts_keys(tmp_path: Path, monkeypatch, caplog):
    """A dotted-path allowlist rule for cli filters out other cli-supplied keys."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\ncli = ["image"]\n',
    )
    parsed = _empty_parsed()
    parsed.image = "cli-img"
    parsed.network = "cli-net"
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(parsed, workdir=tmp_path, environ={})
    assert r.config["image"] == "cli-img"
    assert r.config.get("network") is None
    warnings = [rec.message for rec in caplog.records]
    assert (
        "cli: dropped non-allowlisted keys network — add them to "
        "[config.allowlist].cli to keep them" in warnings
    )
    assert len(warnings) == 1


def test_cli_blocked_by_allowlist(tmp_path: Path, monkeypatch, caplog):
    """Setting cli = false in [config.allowlist] drops all cli-supplied keys."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\nimage = "u"\n[config.allowlist]\ncli = false\n',
    )
    parsed = _empty_parsed()
    parsed.image = "cli-img"
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(parsed, workdir=tmp_path, environ={})
    assert r.config["image"] == "u"
    warnings = [rec.message for rec in caplog.records]
    assert (
        "cli: dropped non-allowlisted keys image — add them to "
        "[config.allowlist].cli to keep them" in warnings
    )
    assert len(warnings) == 1


def test_project_toml_allowlist_restricts_keys(tmp_path: Path, monkeypatch, caplog):
    """A dotted-path allowlist rule for project_toml filters its other keys."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\n[config.allowlist]\nproject_toml = ["image"]\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('image = "p:2"\nnetwork = "p-net"\n')
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "p:2"
    assert r.config.get("network") is None
    warnings = [rec.message for rec in caplog.records]
    assert (
        "project_toml: dropped non-allowlisted keys network — add them to "
        "[config.allowlist].project_toml to keep them" in warnings
    )
    assert len(warnings) == 1


def test_project_toml_invalid_but_blocked_downgraded_to_warning(
    tmp_path: Path, monkeypatch, caplog
):
    """A blocked-by-default project_toml whose load is also invalid does not error."""
    _setup_home(tmp_path, monkeypatch, 'agent = "claude"\nimage = "u"\n')
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text("not = valid = toml")
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "u"


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


def test_dropped_nested_key_warns_with_its_dotted_path(
    tmp_path: Path, monkeypatch, caplog
):
    """A nested key dropped from a kept table is named in full."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'agent = "claude"\n[config.allowlist]\nproject_toml = ["image"]\n',
    )
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ubuntu:22.04\n")
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text(
        f'image = "p:2"\n[build]\ndockerfile = "{dockerfile}"\n'
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "p:2"
    assert r.config.get("build") is None
    warnings = [rec.message for rec in caplog.records]
    assert (
        "project_toml: dropped non-allowlisted keys build.dockerfile — add them "
        "to [config.allowlist].project_toml to keep them" in warnings
    )


def test_root_error_omits_the_empty_key(tmp_path: Path, monkeypatch):
    """A failure with no key (undecodable TOML) reads ``[project_toml]``."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "u"\nagent = "claude"\n[config.allowlist]\nproject_toml = true\n',
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text("not = valid = toml")
    with pytest.raises(ExceptionGroup) as exc:
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    messages = [str(e) for e in exc.value.exceptions]
    assert messages == ["[project_toml] This value is not valid TOML."]


def test_keyed_error_keeps_source_and_key(tmp_path: Path, monkeypatch):
    """A failure on a named key still reads ``[source:key]``."""
    _setup_home(tmp_path, monkeypatch, 'image = "u"\nagent = "claude"\n')
    with pytest.raises(ExceptionGroup) as exc:
        ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_BUILD_POLICY": "bogus"},
        )
    messages = [str(e) for e in exc.value.exceptions]
    assert messages[0].startswith("[env:PADDOCK_BUILD_POLICY] ")


def test_project_toml_relative_paths_resolve_against_workdir(
    tmp_path: Path, monkeypatch
):
    """Relative paths in .paddock/config.toml resolve against the workdir, not
    the cwd, so --workdir from elsewhere still finds them."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n[config.allowlist]\nproject_toml = true\n',
    )
    workdir = tmp_path / "project"
    (workdir / "data").mkdir(parents=True)
    (workdir / "images").mkdir()
    (workdir / "images" / "Dockerfile").write_text("FROM scratch\n")
    sibling = tmp_path / "sibling"
    sibling.mkdir()
    (workdir / ".paddock").mkdir()
    (workdir / ".paddock" / "config.toml").write_text(
        'build.dockerfile = "images/Dockerfile"\n'
        'build.context = "images"\n'
        '[volumes]\n"data" = "/data"\n"../sibling" = "/sibling"\n'
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=workdir.resolve(), environ={})
    assert r.config["build"]["dockerfile"] == (workdir / "images/Dockerfile").resolve()
    assert r.config["build"]["context"] == (workdir / "images").resolve()
    assert set(r.config["volumes"]) == {
        str((workdir / "data").resolve()),
        str(sibling.resolve()),
    }


def test_user_relative_paths_resolve_against_workdir(tmp_path: Path, monkeypatch):
    """Relative paths in the user file's global section resolve against the
    workdir, not the user config directory or the cwd."""
    cfg = _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nbuild.dockerfile = "images/Dockerfile"\n',
    )
    # Decoy: the same path beside the user file must not be picked up.
    (cfg.parent / "images").mkdir()
    (cfg.parent / "images" / "Dockerfile").write_text("FROM scratch\n")
    workdir = tmp_path / "project"
    (workdir / "images").mkdir(parents=True)
    (workdir / "images" / "Dockerfile").write_text("FROM scratch\n")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    assert (
        r.config["build"]["dockerfile"] == (workdir / "images" / "Dockerfile").resolve()
    )


def test_project_overrides_relative_paths_resolve_against_workdir(
    tmp_path: Path, monkeypatch
):
    """Relative paths in a [projects] entry resolve against that project."""
    workdir = (tmp_path / "project").resolve()
    (workdir / "data").mkdir(parents=True)
    _setup_home(
        tmp_path,
        monkeypatch,
        f'image = "i"\n[projects."{workdir}".volumes]\n"data" = "/data"\n',
    )
    monkeypatch.chdir(tmp_path)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    assert set(r.config["volumes"]) == {str(workdir / "data")}


def test_other_project_entry_paths_are_not_checked(tmp_path: Path, monkeypatch):
    """A [projects] entry for another project is checked for shape only, so a
    host path gone from disk can't stop a run elsewhere (ADR 014)."""
    workdir = (tmp_path / "project").resolve()
    workdir.mkdir()
    gone = tmp_path / "gone"
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n'
        f'[projects."{gone}".volumes]\n"data" = "/data"\n"{gone}/abs" = "/abs"\n'
        f'[projects."{gone}".build]\ndockerfile = "Dockerfile"\n',
    )
    monkeypatch.chdir(tmp_path)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    assert "volumes" not in r.config


def test_other_project_entry_shape_errors_stop_the_run(tmp_path: Path, monkeypatch):
    """Shape errors in another project's entry are still reported on every run."""
    workdir = (tmp_path / "project").resolve()
    workdir.mkdir()
    typo = tmp_path / "typo"
    relative = tmp_path / "relative"
    _setup_home(
        tmp_path,
        monkeypatch,
        f'image = "i"\n[projects."{typo}"]\nimgae = "x"\n'
        f'[projects."{relative}".volumes]\n"data" = "/data:xx"\n',
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    labels = sorted(str(e).split("]")[0] + "]" for e in exc_info.value.exceptions)
    assert labels == [
        f"[user:projects.{relative}.volumes.data.mode]",
        f"[user:projects.{typo}.imgae]",
    ]


@pytest.mark.parametrize(
    "key",
    [
        "~/code/widgets",
        "code/widgets",
        "/code/widgets/",
        "/code/../widgets",
        "/code/./w",
        "//code/w",
    ],
)
def test_projects_key_that_cannot_match_stops_the_run(
    tmp_path: Path, monkeypatch, key: str
):
    """A [projects] key that can never equal a resolved workdir is a shape
    error, not an entry silently ignored."""
    workdir = (tmp_path / "project").resolve()
    workdir.mkdir()
    _setup_home(
        tmp_path, monkeypatch, f'image = "i"\n[projects."{key}"]\nimage = "x"\n'
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    assert [str(e).split("]")[0] for e in exc_info.value.exceptions] == [
        f"[user:projects.{key}"
    ]


def test_matching_entry_missing_path_reported_once(tmp_path: Path, monkeypatch):
    """A missing host path in the matching entry is reported by
    project_overrides alone, naming the path checked."""
    workdir = (tmp_path / "project").resolve()
    workdir.mkdir()
    _setup_home(
        tmp_path,
        monkeypatch,
        f'image = "i"\n[projects."{workdir}".volumes]\n"data" = "/data"\n',
    )
    with pytest.raises(ExceptionGroup) as exc_info:
        ConfigLoader().resolve(_empty_parsed(), workdir=workdir, environ={})
    assert [str(e) for e in exc_info.value.exceptions] == [
        "[project_overrides:volumes.data] Path 'data' does not exist or cannot"
        f" be resolved (checked {workdir / 'data'})."
    ]


def test_cli_and_env_relative_paths_resolve_against_workdir(
    tmp_path: Path, monkeypatch
):
    """Env and CLI paths resolve against the workdir, not the cwd, so a value
    means the same thing whichever source sets it."""
    _setup_home(tmp_path, monkeypatch, 'image = "i"\n')
    workdir = tmp_path / "project"
    (workdir / "data").mkdir(parents=True)
    (workdir / "Dockerfile").write_text("FROM scratch\n")
    # Decoys under the cwd must not be picked up.
    cwd = tmp_path / "cwd"
    (cwd / "data").mkdir(parents=True)
    (cwd / "Dockerfile").write_text("FROM scratch\n")
    monkeypatch.chdir(cwd)
    parsed = _empty_parsed()
    parsed.volumes = {"data": "/data"}
    r = ConfigLoader().resolve(
        parsed,
        workdir=workdir,
        environ={"PADDOCK_BUILD_DOCKERFILE": "Dockerfile"},
    )
    assert r.config["build"]["dockerfile"] == (workdir / "Dockerfile").resolve()
    assert set(r.config["volumes"]) == {str((workdir / "data").resolve())}


def _agents_config(tmp_path: Path, project: str) -> str:
    """A user config with a global Claude extra_args and a project entry.

    Args:
        tmp_path: The workdir, whose resolved path keys the project entry.
        project: TOML placed under the workdir's ``[projects]`` entry.
    """
    return (
        'image = "i"\nagent = "claude"\n'
        '[agents.claude]\nextra_args = ["--a", "--b"]\n'
        f'[projects."{tmp_path.resolve()}"]\n{project}'
    )


def test_project_override_replaces_extra_args(tmp_path: Path, monkeypatch):
    """A higher source's extra_args replaces the list; it never concatenates."""
    _setup_home(
        tmp_path,
        monkeypatch,
        _agents_config(tmp_path, 'agents.claude.extra_args = ["--c"]\n'),
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"]["claude"]["extra_args"] == ["--c"]


def test_project_override_clears_extra_args(tmp_path: Path, monkeypatch):
    """An empty list in a higher source clears the inherited one."""
    _setup_home(
        tmp_path,
        monkeypatch,
        _agents_config(tmp_path, "agents.claude.extra_args = []\n"),
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"]["claude"]["extra_args"] == []


def test_agents_settings_merge_per_agent(tmp_path: Path, monkeypatch):
    """Settings for different agents merge; one does not displace another."""
    _setup_home(
        tmp_path,
        monkeypatch,
        _agents_config(tmp_path, 'agents.false.extra_args = ["-l"]\n'),
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"] == {
        "claude": {"extra_args": ["--a", "--b"]},
        "false": {"extra_args": ["-l"]},
    }


def test_another_projects_agents_entry_does_not_apply(tmp_path: Path, monkeypatch):
    """Only the workdir's own [projects] entry contributes agents settings."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        '[projects."/elsewhere".agents.claude]\nextra_args = ["--x"]\n',
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert "agents" not in r.config


def test_env_cannot_set_agents(tmp_path: Path, monkeypatch):
    """agents has no environment form: the variable is an unknown name."""
    _setup_home(tmp_path, monkeypatch, 'image = "i"\nagent = "claude"\n')
    with pytest.raises(ExceptionGroup) as exc:
        ConfigLoader().resolve(
            _empty_parsed(),
            workdir=tmp_path,
            environ={"PADDOCK_AGENTS_CLAUDE_EXTRA_ARGS": "x"},
        )
    assert [str(e) for e in exc.value.exceptions] == [
        "[env:PADDOCK_AGENTS_CLAUDE_EXTRA_ARGS] Unexpected key "
        '"PADDOCK_AGENTS_CLAUDE_EXTRA_ARGS".'
    ]


def _project_file_with_agents(tmp_path: Path) -> None:
    """Write a project file that sets Claude's extra_args."""
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('[agents.claude]\nextra_args = ["--x"]\n')


def test_project_toml_agents_dropped_unless_allowlisted(
    tmp_path: Path, monkeypatch, caplog
):
    """agents is dropped whole, and reported as one path, unless allowlisted."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        '[config.allowlist]\nproject_toml = ["volumes"]\n',
    )
    _project_file_with_agents(tmp_path)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert "agents" not in r.config
    assert [rec.message for rec in caplog.records] == [
        "project_toml: dropped non-allowlisted keys agents — add them to "
        "[config.allowlist].project_toml to keep them"
    ]


def test_project_toml_agents_kept_when_allowlisted(tmp_path: Path, monkeypatch):
    """The single agents directive admits the whole table."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        '[config.allowlist]\nproject_toml = ["agents"]\n',
    )
    _project_file_with_agents(tmp_path)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"]["claude"]["extra_args"] == ["--x"]


def test_user_extra_args_beat_the_project_file(tmp_path: Path, monkeypatch):
    """A user-level extra_args, even empty, wins over the project file's."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        "[agents.claude]\nextra_args = []\n"
        "[config.allowlist]\nproject_toml = true\n",
    )
    _project_file_with_agents(tmp_path)
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"]["claude"]["extra_args"] == []


def test_resolve_reports_the_chosen_agents_extra_args(tmp_path: Path, monkeypatch):
    """The resolved config names the agent's registry key and its extra_args."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        '[agents.claude]\nextra_args = ["--a"]\n'
        '[agents.false]\nextra_args = ["-l"]\n',
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.agent_key == "claude"
    assert r.extra_args == ["--a"]


def test_resolve_keys_the_shell_agent_as_false(tmp_path: Path, monkeypatch):
    """``agent = false`` resolves to the registry key "false" and its settings."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = false\n[agents.false]\nextra_args = ["-l"]\n',
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.agent_key == "false"
    assert r.extra_args == ["-l"]


def test_resolve_has_no_extra_args_without_settings(tmp_path: Path, monkeypatch):
    """An agent with no settings resolves to an empty extra_args."""
    _setup_home(tmp_path, monkeypatch, 'image = "i"\nagent = "claude"\n')
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.extra_args == []


def test_resolve_warns_about_settings_for_an_uninstalled_agent(
    tmp_path: Path, monkeypatch, caplog
):
    """Settings for a name no agent has warn once; installed names do not."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\nagent = "claude"\n'
        '[agents.claud]\nextra_args = ["-x"]\n'
        '[agents.false]\nextra_args = ["-l"]\n',
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert [rec.getMessage() for rec in caplog.records] == [
        '[agents.claud] No agent named "claud" is installed, so its settings '
        "are ignored; installed agents: claude, false"
    ]


class _FakeAgent(BaseAgent):
    """A client that runs nothing, for registry-driven tests."""

    def get_command(self) -> list[str]:
        return [self.AGENT_KEY]

    def get_volumes(self) -> dict:
        return {}


class _FakePaired(_FakeAgent):
    AGENT_KEY = "paired"
    DEFAULT_SERVER = "srv"


class _FakePlain(_FakeAgent):
    AGENT_KEY = "plain"


class _FakeClaude(_FakeAgent):
    AGENT_KEY = "claude"


class _FakeShell(_FakeAgent):
    AGENT_KEY = "false"


def _fake_agents() -> ClassRegistry:
    """A registry of fake clients: paired, plain, claude and false."""
    registry: ClassRegistry = ClassRegistry(attr_name="AGENT_KEY")
    for cls in (_FakePaired, _FakePlain, _FakeClaude, _FakeShell):
        registry.register(cls)
    return registry


def _resolve_agent_config(tmp_path: Path, monkeypatch, config: str) -> ResolvedConfig:
    """Resolve a user config against the fake clients.

    Args:
        tmp_path: The workdir and home.
        monkeypatch: pytest's fixture, to point ``$HOME`` at ``tmp_path``.
        config: TOML appended after an ``image`` line; ``{workdir}`` is
            replaced by the resolved workdir, for a ``[projects]`` key.
    """
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n' + config.replace("{workdir}", str(tmp_path.resolve())),
    )
    return ConfigLoader(agents=_fake_agents()).resolve(
        _empty_parsed(), workdir=tmp_path, environ={}
    )


def test_string_takes_the_clients_default_server(tmp_path: Path, monkeypatch):
    """A name brings that client's default server with it."""
    r = _resolve_agent_config(tmp_path, monkeypatch, 'agent = "paired"\n')
    assert r.agent_key == "paired"
    assert r.server_key == "srv"
    assert r.config["agent"] == {"client": "paired", "server": "srv"}


def test_client_without_a_default_has_no_server(tmp_path: Path, monkeypatch):
    """A client naming no default server resolves to none."""
    r = _resolve_agent_config(tmp_path, monkeypatch, 'agent = "plain"\n')
    assert r.server_key is None
    assert r.config["agent"]["server"] is False


def test_no_agent_defaults_to_claude(tmp_path: Path, monkeypatch):
    """With no agent anywhere the client is claude, with its default server."""
    r = _resolve_agent_config(tmp_path, monkeypatch, "")
    assert r.agent_key == "claude"
    assert r.server_key is None


def test_table_overrides_only_the_server(tmp_path: Path, monkeypatch):
    """A table in a higher source overrides only the half it names."""
    r = _resolve_agent_config(
        tmp_path,
        monkeypatch,
        'agent = "plain"\n[projects."{workdir}"]\nagent = { server = "srv" }\n',
    )
    assert r.agent_key == "plain"
    assert r.server_key == "srv"


def test_client_override_brings_its_default_server(tmp_path: Path, monkeypatch):
    """A client-only override takes the new client's default server."""
    r = _resolve_agent_config(
        tmp_path,
        monkeypatch,
        'agent = "plain"\n[projects."{workdir}"]\nagent = { client = "paired" }\n',
    )
    assert r.agent_key == "paired"
    assert r.server_key == "srv"


def test_string_above_a_table_resets_the_server(tmp_path: Path, monkeypatch):
    """A string in a higher source discards a server a lower source named."""
    r = _resolve_agent_config(
        tmp_path,
        monkeypatch,
        'agent = { server = "srv" }\n[projects."{workdir}"]\nagent = "plain"\n',
    )
    assert r.agent_key == "plain"
    assert r.server_key is None


def test_false_server_survives_a_default(tmp_path: Path, monkeypatch):
    """``server = false`` means none, even for a client with a default."""
    r = _resolve_agent_config(
        tmp_path, monkeypatch, 'agent = { client = "paired", server = false }\n'
    )
    assert r.server_key is None


def test_shell_resets_the_server(tmp_path: Path, monkeypatch):
    """``agent = false`` resets the server as a string does."""
    r = _resolve_agent_config(
        tmp_path,
        monkeypatch,
        'agent = { server = "srv" }\n[projects."{workdir}"]\nagent = false\n',
    )
    assert r.agent_key == "false"
    assert r.server_key is None


def test_unknown_client_resolves_without_a_server(tmp_path: Path, monkeypatch):
    """An uninstalled client is the entry point's to report, not the loader's."""
    r = _resolve_agent_config(tmp_path, monkeypatch, 'agent = "nope"\n')
    assert r.agent_key == "nope"
    assert r.server_key is None


def test_agent_typo_in_table_is_a_config_error(tmp_path: Path, monkeypatch):
    """A misspelt half stops the run at its own key."""
    with pytest.raises(ExceptionGroup) as exc:
        _resolve_agent_config(tmp_path, monkeypatch, 'agent = { clinet = "x" }\n')
    assert any("[user:agent.clinet]" in str(e) for e in exc.value.exceptions)


def _project_file_naming_a_server(tmp_path: Path) -> None:
    """Write a project file whose agent table names server ``srv``."""
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text('agent = { server = "srv" }\n')


def test_project_toml_agent_dropped_whole_unless_allowlisted(
    tmp_path: Path, monkeypatch, caplog
):
    """``agent`` is one directive: dropped whole and reported as one path."""
    _project_file_naming_a_server(tmp_path)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = _resolve_agent_config(
            tmp_path,
            monkeypatch,
            'agent = "plain"\n[config.allowlist]\nproject_toml = ["volumes"]\n',
        )
    assert r.server_key is None
    assert [rec.getMessage() for rec in caplog.records] == [
        "project_toml: dropped non-allowlisted keys agent — add them to "
        "[config.allowlist].project_toml to keep them"
    ]


def test_project_toml_agent_table_kept_when_allowlisted(tmp_path: Path, monkeypatch):
    """A source granted ``agent`` can name a server."""
    _project_file_naming_a_server(tmp_path)
    r = _resolve_agent_config(
        tmp_path,
        monkeypatch,
        '[config.allowlist]\nproject_toml = ["agent"]\n',
    )
    assert r.server_key == "srv"


_PROJECT_FILE_WITH_SERVER_SETTINGS = (
    '[agents.y]\nextra_args = ["-a"]\n[agents.y.server]\nimge = 1\n'
)
_SERVER_SETTINGS_WARNING = (
    "project_toml: ignored agents.y.server — server settings are read only from "
    "the global section of your user config"
)


def _write_project_file(tmp_path: Path, contents: str) -> None:
    """Write ``<tmp_path>/.paddock/config.toml``."""
    pd = tmp_path / ".paddock"
    pd.mkdir()
    (pd / "config.toml").write_text(contents)


def test_project_file_server_settings_warn_and_are_ignored(
    tmp_path: Path, monkeypatch, caplog
):
    """An enabled project file's server settings are ignored with a warning."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n[config.allowlist]\nproject_toml = true\n',
    )
    _write_project_file(tmp_path, _PROJECT_FILE_WITH_SERVER_SETTINGS)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert "server" not in r.config["agents"]["y"]
    assert _SERVER_SETTINGS_WARNING in [rec.getMessage() for rec in caplog.records]


def test_disabled_project_file_server_settings_draw_no_such_warning(
    tmp_path: Path, monkeypatch, caplog
):
    """A disabled project file is ignored whole, server settings included."""
    _setup_home(tmp_path, monkeypatch, 'image = "i"\n')
    _write_project_file(tmp_path, _PROJECT_FILE_WITH_SERVER_SETTINGS)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert not [
        rec
        for rec in caplog.records
        if "server settings are read only" in rec.getMessage()
    ]


def test_user_server_settings_reach_the_merged_config(tmp_path: Path, monkeypatch):
    """Server settings in the user config's global section are merged."""
    _setup_home(
        tmp_path, monkeypatch, 'image = "i"\n[agents.y.server]\nimage = "img"\n'
    )
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["agents"]["y"]["server"]["image"] == "img"


class _FakeClientC(_FakeAgent):
    AGENT_KEY = "c"


class _FakeServerY(BaseServer):
    SERVER_KEY = "y"
    PROTOCOL = "p"
    CONTAINER_PORT = 1

    def get_command(self) -> list[str]:
        return ["y"]

    def is_ready(self, connection: ServerConnection) -> bool:
        return True


def test_settings_warn_per_registry(tmp_path: Path, monkeypatch, caplog):
    """extra_args needs a client of that name, server a server of that name."""
    agents: ClassRegistry = ClassRegistry(attr_name="AGENT_KEY")
    for cls in (_FakeClientC, _FakeClaude, _FakeShell):
        agents.register(cls)
    servers: ClassRegistry = ClassRegistry(attr_name="SERVER_KEY")
    servers.register(_FakeServerY)
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n'
        '[agents.y]\nextra_args = ["-a"]\n[agents.y.server]\nimage = "i"\n'
        '[agents.c]\nextra_args = ["-a"]\n[agents.c.server]\nimage = "i"\n',
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ConfigLoader(agents=agents, servers=servers).resolve(
            _empty_parsed(), workdir=tmp_path, environ={}
        )
    assert [rec.getMessage() for rec in caplog.records] == [
        '[agents.c.server] No server named "c" is installed, so its settings '
        "are ignored; installed servers: y",
        '[agents.y] No agent named "y" is installed, so its settings are '
        "ignored; installed agents: c, claude, false",
    ]


def test_server_settings_warning_reads_none_without_servers(
    tmp_path: Path, monkeypatch, caplog
):
    """With no server installed the list reads ``none``."""
    _setup_home(
        tmp_path, monkeypatch, 'image = "i"\n[agents.claude.server]\nimage = "i"\n'
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert [rec.getMessage() for rec in caplog.records] == [
        '[agents.claude.server] No server named "claude" is installed, so its '
        "settings are ignored; installed servers: none"
    ]


def test_matching_projects_entry_with_server_settings_stops_the_run(
    tmp_path: Path, monkeypatch
):
    """Server settings in a [projects] entry are a validation error."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n'
        f'[projects."{tmp_path.resolve()}".agents.y.server]\nimage = "i"\n',
    )
    with pytest.raises(ExceptionGroup):
        ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})


def test_server_settings_for_an_installed_server_do_not_warn(
    tmp_path: Path, monkeypatch, caplog
):
    """A name holding only server settings needs no client of that name."""
    agents: ClassRegistry = ClassRegistry(attr_name="AGENT_KEY")
    agents.register(_FakeClaude)
    servers: ClassRegistry = ClassRegistry(attr_name="SERVER_KEY")
    servers.register(_FakeServerY)
    _setup_home(tmp_path, monkeypatch, 'image = "i"\n[agents.y.server]\nimage = "i"\n')
    with caplog.at_level(logging.WARNING, logger="paddock"):
        ConfigLoader(agents=agents, servers=servers).resolve(
            _empty_parsed(), workdir=tmp_path, environ={}
        )
    assert [rec.getMessage() for rec in caplog.records] == []


def test_project_file_cannot_grant_itself_access(tmp_path: Path, monkeypatch, caplog):
    """A project file's own allowlist is ignored with a warning (ADR 020).

    The file is granted only volumes; its [config.allowlist] would grant
    everything, and its image must still be dropped.
    """
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "user"\n[config.allowlist]\nproject_toml = ["volumes"]\n',
    )
    _write_project_file(
        tmp_path, 'image = "project"\n[config.allowlist]\nproject_toml = true\n'
    )
    with caplog.at_level(logging.WARNING, logger="paddock"):
        r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.config["image"] == "user"
    assert [rec.getMessage() for rec in caplog.records] == [
        "project_toml: ignored config — only your user config may set it",
        "project_toml: dropped non-allowlisted keys image — add them to "
        "[config.allowlist].project_toml to keep them",
    ]


def test_project_file_cannot_unlock_the_project_dir(tmp_path: Path, monkeypatch):
    """config.project_dir_readonly in a project file changes nothing."""
    _setup_home(
        tmp_path,
        monkeypatch,
        'image = "i"\n[config.allowlist]\nproject_toml = true\n',
    )
    _write_project_file(tmp_path, "[config]\nproject_dir_readonly = false\n")
    r = ConfigLoader().resolve(_empty_parsed(), workdir=tmp_path, environ={})
    assert r.project_dir_readonly is True
