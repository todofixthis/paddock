from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.agent_choice import UNNAMED_SERVER
from paddock.config.context import ConfigContext
from paddock.config.sources.base import Discarded, LoadResult
from paddock.config.sources.project_toml import ProjectTomlSource

# The reasons come from the source: the loader tests pin their wording, as part
# of the whole warning a user reads.
_SERVER_REASON = ProjectTomlSource.SERVER_SETTINGS_REASON
_USER_ONLY_REASON = ProjectTomlSource.USER_ONLY_REASON


def _ctx(tmp_path: Path) -> ConfigContext:
    parsed = ParsedArgs(
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
    return ConfigContext(
        parsed=parsed,
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )


def test_source_key() -> None:
    """SOURCE_KEY is 'project_toml'."""
    assert ProjectTomlSource.SOURCE_KEY == "project_toml"


def test_weight() -> None:
    """WEIGHT is 10."""
    assert ProjectTomlSource.WEIGHT == 10


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    """Missing .paddock/config.toml yields a valid empty instance."""
    result = ProjectTomlSource().load(_ctx(tmp_path))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_load_returns_validated_config(tmp_path: Path) -> None:
    """Valid .paddock/config.toml is loaded and validated."""
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "config.toml").write_text('image = "p:2"\nagent = "claude"\n')
    result = ProjectTomlSource().load(_ctx(tmp_path))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {
        "image": "p:2",
        "agent": {"client": "claude", "server": UNNAMED_SERVER},
    }


def test_load_invalid_toml(tmp_path: Path) -> None:
    """Invalid TOML yields a non-valid instance."""
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "config.toml").write_text("not = valid = toml")
    result = ProjectTomlSource().load(_ctx(tmp_path))
    assert not result.instance.is_valid()


def _load_project_file(tmp_path: Path, contents: str) -> LoadResult:
    """Write a project file and load it."""
    d = tmp_path / ".paddock"
    d.mkdir()
    (d / "config.toml").write_text(contents)
    return ProjectTomlSource().load(_ctx(tmp_path))


def test_server_settings_are_discarded_before_validation(tmp_path: Path) -> None:
    """A project file's server settings never reach validation (ADR 019)."""
    result = _load_project_file(
        tmp_path,
        '[agents.y]\nextra_args = ["-a"]\n[agents.y.server]\nimge = 1\n',
    )
    assert result.instance.is_valid(), result.instance.errors
    assert result.instance.cleaned_data["agents"] == {"y": {"extra_args": ["-a"]}}
    assert result.discarded == [Discarded("agents.y.server", _SERVER_REASON)]


def test_nothing_discarded_without_server_settings(tmp_path: Path) -> None:
    """A project file with no server settings discards nothing."""
    result = _load_project_file(tmp_path, '[agents.y]\nextra_args = ["-a"]\n')
    assert result.discarded == []


def test_non_table_agents_is_left_for_validation(tmp_path: Path) -> None:
    """A malformed ``agents`` is reported by validation, not a crash."""
    result = _load_project_file(tmp_path, "agents = 1\n")
    assert not result.instance.is_valid()
    assert "agents" in result.instance.errors


def test_scalar_server_setting_is_discarded_too(tmp_path: Path) -> None:
    """A ``server`` that is not even a table is discarded, not validated."""
    result = _load_project_file(tmp_path, "[agents.y]\nserver = 1\n")
    assert result.instance.is_valid(), result.instance.errors
    assert result.discarded == [Discarded("agents.y.server", _SERVER_REASON)]


def test_config_is_discarded_before_validation(tmp_path: Path) -> None:
    """A project file cannot grant itself access, nor stop a run by trying."""
    result = _load_project_file(
        tmp_path, 'image = "p"\n[config.allowlist]\nproject_toml = true\n'
    )
    assert result.instance.is_valid(), result.instance.errors
    assert "config" not in result.instance.cleaned_data
    assert result.meta == {}
    assert result.discarded == [Discarded("config", _USER_ONLY_REASON)]


def test_projects_is_discarded_before_validation(tmp_path: Path) -> None:
    """Per-project overrides belong to the user config alone."""
    result = _load_project_file(tmp_path, '[projects."/x"]\nimage = "j"\n')
    assert result.instance.is_valid(), result.instance.errors
    assert "projects" not in result.instance.cleaned_data
    assert result.discarded == [Discarded("projects", _USER_ONLY_REASON)]


def test_malformed_user_only_keys_are_discarded_too(tmp_path: Path) -> None:
    """Nothing under a discarded key is validated, so nothing there stops a run."""
    result = _load_project_file(tmp_path, 'config = 1\nprojects = ["x"]\n')
    assert result.instance.is_valid(), result.instance.errors
    assert result.discarded == [
        Discarded("config", _USER_ONLY_REASON),
        Discarded("projects", _USER_ONLY_REASON),
    ]


def test_misspelt_key_is_still_an_error(tmp_path: Path) -> None:
    """A key that is merely unknown is a typo, and stays a validation error."""
    result = _load_project_file(tmp_path, "[confg]\nx = 1\n")
    assert not result.instance.is_valid()
    assert "confg" in result.instance.errors
    assert result.discarded == []
