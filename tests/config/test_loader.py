from pathlib import Path

import filters as f

from paddock.config.loader import ConfigLoader
from paddock.config.schema import _env_schema


def test_load_missing_file_returns_empty(tmp_path: Path):
    """Missing config files silently yield empty config — no error."""
    loader = ConfigLoader()
    result = loader.load_user_config(tmp_path / "nonexistent.toml")
    assert result == {}


def test_load_user_config(tmp_path: Path):
    """User config values are loaded correctly."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('image = "ubuntu:22.04"\nagent = "claude"\n')
    loader = ConfigLoader()
    result = loader.load_user_config(cfg)
    assert result["image"]["value"] == "ubuntu:22.04"
    assert result["image"]["source"] == str(cfg)


def test_project_config_loaded(tmp_path: Path):
    """Project config is loaded from <workdir>/.paddock/config.toml."""
    paddock_dir = tmp_path / ".paddock"
    paddock_dir.mkdir()
    cfg = paddock_dir / "config.toml"
    cfg.write_text('image = "project:2.0"\nagent = "claude"\n')
    loader = ConfigLoader()
    result = loader.load_project_config(tmp_path)
    assert result["image"]["value"] == "project:2.0"
    assert result["image"]["source"] == str(cfg)


def test_project_overrides_user(tmp_path: Path):
    """Project config values overwrite user config values during resolve()."""
    user_cfg = tmp_path / "user.toml"
    user_cfg.write_text('image = "base:1.0"\nagent = "claude"\n')

    paddock_dir = tmp_path / ".paddock"
    paddock_dir.mkdir()
    (paddock_dir / "config.toml").write_text('image = "project:2.0"\n')

    loader = ConfigLoader()
    user = loader.load_user_config(user_cfg)
    project = loader.load_project_config(tmp_path)
    merged = loader._merge_sourced([user, project])
    assert merged["image"]["value"] == "project:2.0"
    assert merged["agent"]["value"] == "claude"


def test_volumes_are_additive(tmp_path: Path):
    """Volumes from multiple sources merge by host path; later sources win on conflict."""
    user_cfg = tmp_path / "user.toml"
    user_cfg.write_text(
        '[volumes]\n"/host/a" = "/container/a"\n"/host/conflict" = "/old"\n'
    )

    project_dir = tmp_path / ".paddock"
    project_dir.mkdir()
    (project_dir / "config.toml").write_text(
        '[volumes]\n"/host/b" = "/container/b"\n"/host/conflict" = "/new"\n'
    )

    loader = ConfigLoader()
    user = loader.load_user_config(user_cfg)
    project = loader.load_project_config(tmp_path)
    merged = loader._merge_sourced([user, project])
    values = loader._extract_values(merged)
    assert values["volumes"]["/host/a"] == "/container/a"
    assert values["volumes"]["/host/b"] == "/container/b"
    assert values["volumes"]["/host/conflict"] == "/new"


def test_config_from_env(tmp_path: Path):
    """PADDOCK_* env vars are extracted and keyed correctly."""
    loader = ConfigLoader()
    result = loader.config_from_env(
        {"PADDOCK_IMAGE": "myimage:latest", "OTHER": "ignored"}
    )
    assert result["image"]["value"] == "myimage:latest"
    assert result["image"]["source"] == "env:PADDOCK_IMAGE"


def test_config_from_env_nested(tmp_path: Path):
    """PADDOCK_BUILD_DOCKERFILE maps to build.dockerfile."""
    loader = ConfigLoader()
    result = loader.config_from_env({"PADDOCK_BUILD_DOCKERFILE": "/path/Dockerfile"})
    assert result["build"]["dockerfile"]["value"] == "/path/Dockerfile"


def test_apply_defaults(tmp_path: Path):
    """Default values are set when not supplied by any config source."""
    loader = ConfigLoader()
    result = loader._apply_defaults({})
    assert result["agent"] == "claude"
    assert result["build"] is None
    assert result["network"] is None
    assert result["volumes"] == {}


def test_resolve_returns_valid_runner(tmp_path: Path, monkeypatch):
    """resolve() with a valid config returns a FilterRunner where is_valid() is True."""
    paddock_dir = tmp_path / ".paddock"
    paddock_dir.mkdir()
    (paddock_dir / "config.toml").write_text(
        'image = "ubuntu:22.04"\nagent = "claude"\n'
    )

    class FakeParsed:
        agent = None
        build_args = {}
        build_context = None
        build_dockerfile = None
        build_policy = None
        command = []
        config_file = None
        dry_run = False
        image = None
        network = None
        quiet = False
        volumes = {}
        workdir = None

    loader = ConfigLoader()
    runner = loader.resolve(FakeParsed(), workdir=tmp_path, environ={})
    assert runner.is_valid()
    assert runner.cleaned_data["image"] == "ubuntu:22.04"


# ---------------------------------------------------------------------------
# _env_schema
# ---------------------------------------------------------------------------


def test_env_schema_expands_tilde_in_config_file(monkeypatch, tmp_path):
    """PADDOCK_CONFIG_FILE with a leading tilde is expanded by the env schema."""
    monkeypatch.setenv("HOME", str(tmp_path))
    config_file = tmp_path / "extra.toml"
    config_file.write_text("")
    runner = f.FilterRunner(_env_schema, {"PADDOCK_CONFIG_FILE": "~/extra.toml"})
    assert runner.is_valid()
    assert runner.cleaned_data["PADDOCK_CONFIG_FILE"] == config_file.resolve()


def test_env_schema_expands_tilde_in_dockerfile(monkeypatch, tmp_path):
    """PADDOCK_BUILD_DOCKERFILE with a leading tilde is expanded by the env schema."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    runner = f.FilterRunner(_env_schema, {"PADDOCK_BUILD_DOCKERFILE": "~/Dockerfile"})
    assert runner.is_valid()
    assert runner.cleaned_data["PADDOCK_BUILD_DOCKERFILE"] == dockerfile.resolve()


def test_env_schema_rejects_empty_dockerfile():
    """PADDOCK_BUILD_DOCKERFILE="" is rejected — empty string would silently resolve to CWD."""
    runner = f.FilterRunner(_env_schema, {"PADDOCK_BUILD_DOCKERFILE": ""})
    assert not runner.is_valid()


def test_env_schema_rejects_empty_context():
    """PADDOCK_BUILD_CONTEXT="" is rejected — empty string would silently resolve to CWD."""
    runner = f.FilterRunner(_env_schema, {"PADDOCK_BUILD_CONTEXT": ""})
    assert not runner.is_valid()


def test_env_schema_rejects_invalid_policy():
    """PADDOCK_BUILD_POLICY with an unrecognised value is invalid."""
    runner = f.FilterRunner(_env_schema, {"PADDOCK_BUILD_POLICY": "never"})
    assert not runner.is_valid()


def test_env_schema_ignores_non_paddock_vars():
    """Non-PADDOCK_* vars in the env are silently ignored."""
    runner = f.FilterRunner(_env_schema, {"PATH": "/usr/bin", "HOME": "/home/user"})
    assert runner.is_valid()


def test_env_build_args_not_mapped(tmp_path):
    """PADDOCK_BUILD_ARGS is silently ignored — it cannot express a key=value dict as a single env var."""
    paddock_dir = tmp_path / ".paddock"
    paddock_dir.mkdir()
    (paddock_dir / "config.toml").write_text(
        'image = "ubuntu:22.04"\nagent = "claude"\n'
    )

    class FakeParsed:
        agent = None
        build_args = {}
        build_context = None
        build_dockerfile = None
        build_policy = None
        command = []
        config_file = None
        dry_run = False
        image = None
        network = None
        quiet = False
        volumes = {}
        workdir = None

    runner = ConfigLoader().resolve(
        FakeParsed(), workdir=tmp_path, environ={"PADDOCK_BUILD_ARGS": "FOO=bar"}
    )
    assert runner.is_valid()
    assert runner.cleaned_data["build"] is None


def test_loader_resolve_env_dockerfile_tilde_expanded(monkeypatch, tmp_path):
    """A tilde in PADDOCK_BUILD_DOCKERFILE is expanded through ConfigLoader.resolve()."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    monkeypatch.setenv("PADDOCK_BUILD_DOCKERFILE", "~/Dockerfile")
    monkeypatch.setenv("PADDOCK_IMAGE", "myimage")
    monkeypatch.setenv("PADDOCK_AGENT", "claude")

    class FakeParsed:
        agent = None
        build_args = {}
        build_context = None
        build_dockerfile = None
        build_policy = None
        command = []
        config_file = None
        dry_run = False
        image = None
        network = None
        quiet = False
        volumes = {}
        workdir = None

    runner = ConfigLoader().resolve(FakeParsed(), workdir=tmp_path)
    assert runner.is_valid()
    assert runner.cleaned_data["build"]["dockerfile"] == dockerfile.resolve()
