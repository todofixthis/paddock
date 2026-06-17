from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.allowlist import Allowlist
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


def test_source_key():
    """SOURCE_KEY is 'cli'."""
    assert CliConfigSource.SOURCE_KEY == "cli"


def test_weight():
    """WEIGHT is 60."""
    assert CliConfigSource.WEIGHT == 60


def test_empty_parsed_returns_empty(tmp_path):
    """All-None parsed args yield a valid empty runner."""
    runner = CliConfigSource().load(_ctx(tmp_path, _empty()))
    assert runner.is_valid()
    assert runner.cleaned_data == {}


def test_image_extracted(tmp_path):
    """--image maps to cleaned_data['image']."""
    p = _empty()
    p.image = "x:1"
    runner = CliConfigSource().load(_ctx(tmp_path, p))
    assert runner.cleaned_data == {"image": "x:1"}


def test_build_args_extracted(tmp_path):
    """--build-arg maps to cleaned_data['build']['args']."""
    p = _empty()
    p.build_args = {"FOO": "bar"}
    runner = CliConfigSource().load(_ctx(tmp_path, p))
    assert runner.cleaned_data["build"]["args"] == {"FOO": "bar"}


def test_sanitise_filters_by_allowlist(tmp_path):
    p = _empty()
    p.image = "x:1"
    p.network = "y"
    runner = CliConfigSource().load(_ctx(tmp_path, p))
    a = Allowlist({"cli": ["image"]})
    s = CliConfigSource().sanitise(runner, a)
    assert s.cleaned_data == {"image": "x:1"}


def test_sanitise_blocked_source_returns_empty(tmp_path):
    p = _empty()
    p.image = "x:1"
    runner = CliConfigSource().load(_ctx(tmp_path, p))
    s = CliConfigSource().sanitise(runner, Allowlist({"cli": False}))
    assert s.cleaned_data == {}
