from pathlib import Path

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.env import EnvConfigSource


def _ctx(tmp_path: Path, environ: dict) -> ConfigContext:
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
        environ=environ,
        workdir=tmp_path,
        user_config_path=tmp_path / "u.toml",
    )


def test_source_key():
    """SOURCE_KEY is 'env'."""
    assert EnvConfigSource.SOURCE_KEY == "env"


def test_weight():
    """WEIGHT is 50."""
    assert EnvConfigSource.WEIGHT == 50


def test_prefix_is_class_property():
    """PREFIX constant is PADDOCK_."""
    assert EnvConfigSource.PREFIX == "PADDOCK_"


def test_empty_environ(tmp_path):
    """Empty environ yields a valid empty runner."""
    runner = EnvConfigSource().load(_ctx(tmp_path, {}))
    assert runner.is_valid()
    assert runner.cleaned_data == {}


def test_image_extracted(tmp_path):
    """PADDOCK_IMAGE maps to cleaned_data['image']."""
    runner = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_IMAGE": "x:1"}))
    assert runner.is_valid()
    assert runner.cleaned_data == {"image": "x:1"}


def test_nested_keys_extracted(tmp_path):
    """PADDOCK_BUILD_DOCKERFILE maps to cleaned_data['build']['dockerfile']."""
    df = tmp_path / "Dockerfile"
    df.write_text("FROM x")
    runner = EnvConfigSource().load(
        _ctx(tmp_path, {"PADDOCK_BUILD_DOCKERFILE": str(df)})
    )
    assert runner.is_valid()
    assert runner.cleaned_data["build"]["dockerfile"] == df.resolve()


def test_invalid_build_policy_surfaces(tmp_path):
    """Env-shape validation happens inside the source; bad value yields an invalid runner."""
    runner = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_BUILD_POLICY": "bogus"}))
    assert not runner.is_valid()


def test_non_paddock_vars_ignored(tmp_path):
    """Non-PADDOCK_* env vars are silently ignored."""
    runner = EnvConfigSource().load(_ctx(tmp_path, {"PATH": "/usr/bin"}))
    assert runner.cleaned_data == {}


def test_loader_keys_are_skipped(tmp_path):
    """PADDOCK_CONFIG_FILE and PADDOCK_BUILD_ARGS are handled by other sources."""
    runner = EnvConfigSource().load(
        _ctx(tmp_path, {"PADDOCK_CONFIG_FILE": "/x", "PADDOCK_BUILD_ARGS": "foo"})
    )
    assert runner.cleaned_data == {}
