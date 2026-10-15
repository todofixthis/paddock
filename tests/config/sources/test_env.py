from pathlib import Path

import filters as f

from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.filters import NoEnvForm
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


def test_build_args_bare_name_rejected(tmp_path):
    """PADDOCK_BUILD_ARGS is an error, not silently ignored."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_BUILD_ARGS": "foo"}))
    assert result.instance.error_codes == {
        "PADDOCK_BUILD_ARGS": [NoEnvForm.CODE_NO_ENV_FORM]
    }


def test_build_args_suffixed_name_rejected(tmp_path):
    """PADDOCK_BUILD_ARGS_<NAME> is an error, not split into nested build.args."""
    df = tmp_path / "Dockerfile"
    df.write_text("FROM x")
    result = EnvConfigSource().load(
        _ctx(
            tmp_path,
            {
                "PADDOCK_BUILD_ARGS_NODE_VERSION": "24",
                "PADDOCK_BUILD_DOCKERFILE": str(df),
            },
        )
    )
    assert result.instance.error_codes == {
        "PADDOCK_BUILD_ARGS_NODE_VERSION": [NoEnvForm.CODE_NO_ENV_FORM]
    }


def test_volumes_bare_name_rejected(tmp_path):
    """PADDOCK_VOLUMES names the CLI/TOML alternatives instead of a type error."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_VOLUMES": "/x"}))
    assert result.instance.error_codes == {
        "PADDOCK_VOLUMES": [NoEnvForm.CODE_NO_ENV_FORM]
    }


def test_volumes_suffixed_name_rejected(tmp_path, monkeypatch):
    """PADDOCK_VOLUMES_<NAME> is an error, not a mount of the relative path <name>."""
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(tmp_path)
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_VOLUMES_TMP": "/x"}))
    assert result.instance.error_codes == {
        "PADDOCK_VOLUMES_TMP": [NoEnvForm.CODE_NO_ENV_FORM]
    }


def test_no_env_form_needs_separator(tmp_path):
    """A name merely starting with PADDOCK_BUILD_ARGS is an ordinary unknown key."""
    result = EnvConfigSource().load(_ctx(tmp_path, {"PADDOCK_BUILD_ARGSX": "1"}))
    assert result.instance.error_codes == {
        "build.argsx": [f.FilterMapper.CODE_EXTRA_KEY]
    }


def test_no_env_form_empty_value_ignored(tmp_path):
    """An empty PADDOCK_BUILD_ARGS counts as unset, like any empty PADDOCK_*."""
    result = EnvConfigSource().load(
        _ctx(tmp_path, {"PADDOCK_BUILD_ARGS": "", "PADDOCK_VOLUMES_TMP": ""})
    )
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}
