from pathlib import Path

import filters as f
import pytest

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.env import EnvConfigSource


def _ctx(tmp_path: Path, environ: dict) -> ConfigContext:
    parsed = ParsedArgs(
        agent=None,
        agent_args=[],
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
    """Empty environ yields a valid empty instance."""
    result = EnvConfigSource().load(_ctx(tmp_path, {}))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_image_extracted(tmp_path):
    """PADDOCK_IMAGE maps to cleaned_data['image']."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_IMAGE": "x:1"}))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {"image": "x:1"}


def test_nested_keys_extracted(tmp_path):
    """PADDOCK_BUILD_DOCKERFILE maps to cleaned_data['build']['dockerfile']."""
    df = tmp_path / "Dockerfile"
    df.write_text("FROM x")
    result = EnvConfigSource().load(
        _ctx(tmp_path, {"PADDOCK_BUILD_DOCKERFILE": str(df)})
    )
    assert result.instance.is_valid()
    assert result.instance.cleaned_data["build"]["dockerfile"] == df.resolve()


def test_invalid_build_policy_surfaces(tmp_path):
    """Env-shape validation happens inside the source; bad value yields an invalid instance."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_BUILD_POLICY": "bogus"}))
    assert not result.instance.is_valid()


def test_non_paddock_vars_ignored(tmp_path):
    """Non-PADDOCK_* env vars are silently ignored."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PATH": "/usr/bin"}))
    assert result.instance.cleaned_data == {}


@pytest.mark.parametrize(
    "name",
    [
        "PADDOCK_BUILD_ARGS",
        "PADDOCK_BUILD_ARGS_NODE_VERSION",
        "PADDOCK_BUILD_ARGSX",
        "PADDOCK_IMGAE",
        "PADDOCK_VOLUMES",
        "PADDOCK_VOLUMES_TMP",
    ],
)
def test_unknown_name_rejected(tmp_path, name):
    """A PADDOCK_* name with no directive is an error, keyed on the name itself.

    Covers the free-form maps (``build.args``, ``volumes``), whose suffixed
    names would otherwise split on ``_`` into nested keys.
    """
    result = EnvConfigSource().load(_ctx(tmp_path, {name: "1"}))
    assert result.instance.error_codes == {name: [f.FilterMapper.CODE_EXTRA_KEY]}


def test_unknown_name_rejected_when_empty(tmp_path):
    """An unknown name is rejected even with an empty value."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_BUILD_ARGS": ""}))
    assert result.instance.error_codes == {
        "PADDOCK_BUILD_ARGS": [f.FilterMapper.CODE_EXTRA_KEY]
    }
