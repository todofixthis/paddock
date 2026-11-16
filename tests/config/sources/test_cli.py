from dataclasses import replace
from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.cli import CliConfigSource


def _ctx(tmp_path: Path, parsed: ParsedArgs) -> ConfigContext:
    return ConfigContext(
        parsed=parsed,
        environ={},
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )


def _empty() -> ParsedArgs:
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


def test_source_key():
    """SOURCE_KEY is 'cli'."""
    assert CliConfigSource.SOURCE_KEY == "cli"


def test_weight():
    """WEIGHT is 60."""
    assert CliConfigSource.WEIGHT == 60


def test_empty_parsed_returns_empty(tmp_path):
    """All-None parsed args yield a valid empty instance."""
    result = CliConfigSource().load(_ctx(tmp_path, _empty()))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_image_extracted(tmp_path):
    """--image maps to cleaned_data['image']."""
    p = _empty()
    p.image = "x:1"
    result = CliConfigSource().load(_ctx(tmp_path, p))
    assert result.instance.cleaned_data == {"image": "x:1"}


def test_build_args_extracted(tmp_path):
    """--build-arg maps to cleaned_data['build']['args']."""
    p = _empty()
    p.build_args = {"FOO": "bar"}
    result = CliConfigSource().load(_ctx(tmp_path, p))
    assert result.instance.cleaned_data["build"]["args"] == {"FOO": "bar"}


def _agent(tmp_path, **halves):
    """Load the CLI source with the given agent flags and return its agent."""
    result = CliConfigSource().load(_ctx(tmp_path, replace(_empty(), **halves)))
    assert result.instance.is_valid(), result.instance.errors
    return result.instance.cleaned_data["agent"]


def test_agent_whole_then_half(tmp_path):
    """--agent applies first, then --agent-server names its half."""
    assert _agent(tmp_path, agent="claude", agent_server="srv") == {
        "client": "claude",
        "server": "srv",
    }


def test_agent_half_alone(tmp_path):
    """--agent-client alone names only the client."""
    assert _agent(tmp_path, agent_client="x") == {"client": "x"}


def test_agent_server_false(tmp_path):
    """--agent-server=false means no server."""
    assert _agent(tmp_path, agent_server="false") == {"server": False}
