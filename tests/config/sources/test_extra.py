from paddock.cli import ParsedArgs
from paddock.config.context import ConfigContext
from paddock.config.sources.extra import ExtraConfigSource


def _ctx(tmp_path, parsed, environ) -> ConfigContext:
    return ConfigContext(
        parsed=parsed,
        environ=environ,
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
    """SOURCE_KEY is 'extra'."""
    assert ExtraConfigSource.SOURCE_KEY == "extra"


def test_weight():
    """WEIGHT is 40."""
    assert ExtraConfigSource.WEIGHT == 40


def test_no_path_returns_empty(tmp_path):
    """No config-file path configured yields a valid empty instance."""
    result = ExtraConfigSource().load(_ctx(tmp_path, _empty(), {}))
    assert result.instance.cleaned_data == {}


def test_missing_file_returns_empty(tmp_path):
    """A path naming a file that does not exist yields a valid empty instance."""
    p = _empty()
    p.config_file = str(tmp_path / "absent.toml")
    result = ExtraConfigSource().load(_ctx(tmp_path, p, {}))
    assert result.instance.is_valid()
    assert result.instance.cleaned_data == {}


def test_strips_meta_sections(tmp_path):
    """[projects] and [config] in an extra file are ignored; globals survive."""
    cfg = tmp_path / "extra.toml"
    cfg.write_text(
        'image = "e:1"\n'
        "\n"
        '[projects."/somewhere"]\n'
        'image = "ignored:1"\n'
        "\n"
        "[config.allowlist]\n"
        "project_toml = true\n"
    )
    p = _empty()
    p.config_file = str(cfg)
    result = ExtraConfigSource().load(_ctx(tmp_path, p, {}))
    assert result.instance.cleaned_data == {"image": "e:1"}
    assert result.meta == {}


def test_env_path(tmp_path):
    """PADDOCK_CONFIG_FILE env var is used when no CLI path is set."""
    cfg = tmp_path / "extra.toml"
    cfg.write_text('image = "e:1"\n')
    result = ExtraConfigSource().load(
        _ctx(tmp_path, _empty(), {"PADDOCK_CONFIG_FILE": str(cfg)})
    )
    assert result.instance.cleaned_data == {"image": "e:1"}


def test_cli_wins_over_env(tmp_path):
    """CLI --config-file takes precedence over PADDOCK_CONFIG_FILE."""
    a = tmp_path / "a.toml"
    a.write_text('image = "a"\n')
    b = tmp_path / "b.toml"
    b.write_text('image = "b"\n')
    p = _empty()
    p.config_file = str(a)
    result = ExtraConfigSource().load(
        _ctx(tmp_path, p, {"PADDOCK_CONFIG_FILE": str(b)})
    )
    assert result.instance.cleaned_data == {"image": "a"}
