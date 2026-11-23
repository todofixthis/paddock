from collections.abc import Callable
from pathlib import Path

import filters as f
import pytest
from filters.handlers import FilterRunner
from filters.pytest import skip_value_check

from paddock.config.agent_choice import UNNAMED_SERVER
from paddock.config.fields import CONFIG_FIELDS, allowlist_directives
from paddock.config.filters import AbsoluteHostPath, VolumeSpec
from paddock.config.schema import (
    BUILD_POLICIES,
    ConfigSchema,
    config_meta_schema,
    standard_config_schema,
    user_config_schema,
)


def _validate(config: dict) -> dict:
    """Run ConfigSchema with the cwd as base; these configs hold no relative
    paths, so the base only satisfies the required argument."""
    return ConfigSchema().validate(config, base_dir=Path.cwd())


def test_valid_minimal() -> None:
    """Minimal valid config passes; absent optional fields are stripped by DropEmpty."""
    result = _validate({"image": "ubuntu:22.04", "agent": "claude"})
    assert result["image"] == "ubuntu:22.04"
    assert result["agent"] == {"client": "claude", "server": UNNAMED_SERVER}


def test_invalid_empty_image() -> None:
    """An empty string is not a valid image name."""
    with pytest.raises(SystemExit):
        _validate({"image": "", "agent": "claude"})


def test_invalid_missing_image() -> None:
    """image is required — omitting it should fail."""
    with pytest.raises(SystemExit):
        _validate({"agent": "claude"})


def test_agent_false() -> None:
    """agent = False (bool) enables shell mode."""
    result = _validate({"image": "ubuntu:22.04", "agent": False})
    assert result["agent"] == {"client": False, "server": UNNAMED_SERVER}


def test_unknown_key_rejected() -> None:
    """Unknown config keys indicate a typo and should be rejected."""
    with pytest.raises(SystemExit):
        _validate({"image": "ubuntu:22.04", "agent": "claude", "typo": "oops"})


def test_valid_build_config(tmp_path: Path) -> None:
    """build config with all fields valid."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    config = {
        "image": "myapp:latest",
        "agent": "claude",
        "build": {
            "dockerfile": str(dockerfile),
            "context": None,
            "policy": "if-missing",
        },
    }
    result = _validate(config)
    assert result["build"]["policy"] == "if-missing"


def test_build_policy_without_dockerfile_is_valid() -> None:
    """A policy alone is valid: it pulls the image rather than building it."""
    result = _validate(
        {
            "image": "ghcr.io/example/agent:python",
            "agent": "claude",
            "build": {"policy": "daily"},
        }
    )
    assert result["build"] == {"policy": "daily"}


def test_empty_build_dockerfile_rejected() -> None:
    """An empty dockerfile is a mistake, not a request to pull."""
    with pytest.raises(SystemExit):
        _validate(
            {
                "image": "myapp:latest",
                "agent": "claude",
                "build": {"dockerfile": "", "policy": "daily"},
            }
        )


def test_valid_build_args(tmp_path: Path) -> None:
    """build.args accepts arbitrary key-value pairs (user-defined Dockerfile ARGs)."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    config = {
        "image": "myapp:latest",
        "agent": "claude",
        "build": {
            "dockerfile": str(dockerfile),
            "args": {"FOO": "bar", "PYTHON_VERSION": "3.13"},
        },
    }
    result = _validate(config)
    assert result["build"]["args"] == {"FOO": "bar", "PYTHON_VERSION": "3.13"}


def test_valid_volumes(tmp_path: Path) -> None:
    """
    Volumes can be specified as a bare path (implicit :ro), explicit :ro, or explicit :rw.
    Host paths are resolved by VolumeMap; bare container paths get ':ro' appended.
    """
    implicit = tmp_path / "implicit"
    implicit.mkdir()
    explicit_ro = tmp_path / "explicit-ro"
    explicit_ro.mkdir()
    explicit_rw = tmp_path / "explicit-rw"
    explicit_rw.mkdir()

    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {
            str(implicit): "/container/implicit",
            str(explicit_ro): "/container/ro:ro",
            str(explicit_rw): "/container/rw:rw",
        },
    }
    result = _validate(config)
    assert result["volumes"][str(implicit.resolve())] == VolumeSpec(
        "/container/implicit", "ro"
    )
    assert result["volumes"][str(explicit_ro.resolve())] == VolumeSpec(
        "/container/ro", "ro"
    )
    assert result["volumes"][str(explicit_rw.resolve())] == VolumeSpec(
        "/container/rw", "rw"
    )


def test_invalid_volume_value() -> None:
    """A volume destination with more than one colon segment is invalid."""
    with pytest.raises(SystemExit):
        _validate(
            {
                "image": "ubuntu:22.04",
                "agent": "claude",
                "volumes": {"/host": "not:a:valid:path"},
            }
        )


def test_build_dockerfile_tilde_expanded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """'~/Dockerfile' is expanded using Path.home()."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": "~/Dockerfile"},
        "image": "myimage",
    }
    result = f.FilterRunner(
        standard_config_schema(base_dir=Path.cwd(), merged=True), raw
    )
    assert result.is_valid()
    assert not str(result.cleaned_data["build"]["dockerfile"]).startswith("~")


def test_build_context_tilde_expanded(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tilde in build.context is expanded and resolved."""
    monkeypatch.setenv("HOME", str(tmp_path))
    context_dir = tmp_path / "myproject"
    context_dir.mkdir()
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": "~/Dockerfile", "context": "~/myproject"},
        "image": "myimage",
    }
    result = f.FilterRunner(
        standard_config_schema(base_dir=Path.cwd(), merged=True), raw
    )
    assert result.is_valid()
    assert not str(result.cleaned_data["build"]["context"]).startswith("~")


def test_build_context_none_unchanged(tmp_path: Path) -> None:
    """None context is stripped by DropEmpty; the build section remains valid."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": str(dockerfile), "context": None},
        "image": "myimage",
    }
    result = f.FilterRunner(
        standard_config_schema(base_dir=Path.cwd(), merged=True), raw
    )
    assert result.is_valid()
    assert result.cleaned_data["build"].get("context") is None


def test_standard_schema_non_merged_accepts_minimal(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """In per-source mode the schema accepts arbitrarily incomplete configs."""
    assert_filter_passes(
        standard_config_schema(base_dir=Path.cwd(), merged=False),
        {"image": "ubuntu:22.04"},
        skip_value_check,
    )


def test_standard_schema_non_merged_accepts_empty(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """Per-source mode allows an entirely empty dict — sources may contribute nothing."""
    assert_filter_passes(
        standard_config_schema(base_dir=Path.cwd(), merged=False), {}, skip_value_check
    )


def test_standard_schema_merged_requires_image(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """In merged mode ``image`` is required."""
    assert_filter_errors(
        standard_config_schema(base_dir=Path.cwd(), merged=True),
        {"agent": "claude"},
        {"image": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_standard_schema_merged_requires_agent(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """In merged mode ``agent`` is required."""
    assert_filter_errors(
        standard_config_schema(base_dir=Path.cwd(), merged=True),
        {"image": "x"},
        {"agent": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_standard_schema_rejects_unknown_top_level_key(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """Unknown top-level keys indicate a typo and should be rejected."""
    assert_filter_errors(
        standard_config_schema(base_dir=Path.cwd(), merged=False),
        {"image": "x", "wat": "no"},
        {"wat": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_standard_schema_with_extra_keys_macro(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """``extra_keys`` allows additional top-level keys such as ``config``."""
    schema = standard_config_schema(
        base_dir=Path.cwd(), extra_keys={"config": config_meta_schema}, merged=False
    )
    assert_filter_passes(
        schema,
        {"image": "x", "config": {"allowlist": {"project_toml": True}}},
        skip_value_check,
    )


def test_user_config_schema_accepts_projects_and_config(
    assert_filter_passes: Callable[..., FilterRunner], tmp_path: Path
) -> None:
    """user_config_schema accepts projects and config sections."""
    assert_filter_passes(
        user_config_schema(base_dir=tmp_path),
        'image = "base:1.0"\nagent = "claude"\n'
        '[projects."/abs/path"]\nimage = "p:2"\n'
        "[config.allowlist]\nproject_toml = true\n",
        skip_value_check,
    )


def test_user_config_schema_rejects_unknown_allowlist_source(
    assert_filter_errors: Callable[..., FilterRunner], tmp_path: Path
) -> None:
    """Unknown allowlist source keys are rejected."""
    assert_filter_errors(
        user_config_schema(base_dir=tmp_path),
        'agent = "claude"\nimage = "x"\n[config.allowlist]\nfoo = true\n',
        {"config.allowlist.foo": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_allowlist_entry_accepts_true(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """AllowlistEntry accepts the boolean ``True``."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_passes(AllowlistEntry, True, True)


def test_allowlist_entry_accepts_known_dotted_paths(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """AllowlistEntry accepts a list of known dotted paths."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_passes(
        AllowlistEntry, ["image", "build.dockerfile"], skip_value_check
    )


def test_allowlist_entry_rejects_unknown_dotted_path(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """AllowlistEntry rejects unknown dotted paths."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_errors(
        AllowlistEntry, ["bogus"], {"0": [f.Choice.CODE_INVALID]}, skip_value_check
    )


def test_allowlist_entry_rejects_a_path_under_agents(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """``agents`` is one directive: no dotted path descends into it (ADR 017)."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_errors(
        AllowlistEntry,
        ["agents.claude"],
        {"0": [f.Choice.CODE_INVALID]},
        skip_value_check,
    )


def test_every_directive_is_accepted_by_the_schema(tmp_path: Path) -> None:
    """Each declared directive round-trips through the real schema."""
    # Top-level keys whose schema value is itself a mapping (nested build
    # keys, or the volumes dict) need a dict placeholder; ``build.context``
    # and ``build.dockerfile`` are filesystem paths validated by ``Filepath``
    # and need a real directory/file; every other directive is a scalar leaf
    # and accepts a plain string.
    mapping_valued = {
        "agents",
        "volumes",
        *(key for key, subs in CONFIG_FIELDS.items() if subs),
    }
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    path_leaves = {"build.context": str(tmp_path), "build.dockerfile": str(dockerfile)}
    other_leaves: dict[str, object] = {
        "build.args": ["x"],
        "build.policy": BUILD_POLICIES[0],
    }
    for directive in allowlist_directives():
        parts = directive.split(".")
        config: dict = {}
        node = config
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        if directive in path_leaves:
            leaf_value: object = path_leaves[directive]
        elif directive in other_leaves:
            leaf_value = other_leaves[directive]
        elif len(parts) == 1 and parts[0] in mapping_valued:
            leaf_value = {}
        else:
            leaf_value = "x"
        node[parts[-1]] = leaf_value
        runner = f.FilterRunner(
            standard_config_schema(base_dir=Path.cwd(), merged=False), config
        )
        assert runner.is_valid(), (directive, runner.errors)


def test_unknown_nested_key_is_rejected() -> None:
    """A path outside the declaration fails schema validation."""
    runner = f.FilterRunner(
        standard_config_schema(base_dir=Path.cwd(), merged=False),
        {"build": {"bogus": "x"}},
    )
    assert not runner.is_valid()


def _per_source_schema():
    """The per-source standard schema; these configs hold no relative paths."""
    return standard_config_schema(base_dir=Path.cwd(), merged=False)


def test_agents_accepts_extra_args(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """extra_args is a list of strings, kept verbatim, spaces and blanks too."""
    config = {"agents": {"claude": {"extra_args": ["--resume", "a b", ""]}}}
    assert_filter_passes(_per_source_schema(), config, config)


def test_agents_accepts_a_name_no_agent_has(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """The schema never consults the registry; unknown names warn later."""
    config = {"agents": {"claud": {"extra_args": ["-x"]}}}
    assert_filter_passes(_per_source_schema(), config, config)


def test_agents_keeps_an_empty_list(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """An empty extra_args survives DropEmpty, so it can clear a lower list."""
    config: dict = {"agents": {"claude": {"extra_args": []}}}
    assert_filter_passes(_per_source_schema(), config, config)


def test_agents_rejects_a_string_extra_args(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """A string is not split into arguments, nor into characters."""
    assert_filter_errors(
        _per_source_schema(),
        {"agents": {"claude": {"extra_args": "--resume"}}},
        {"agents.claude.extra_args": [f.Type.CODE_WRONG_TYPE]},
        skip_value_check,
    )


def test_agents_rejects_a_non_string_entry(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """Entries are not coerced: an integer is an error, not ``"1"``."""
    assert_filter_errors(
        _per_source_schema(),
        {"agents": {"claude": {"extra_args": ["a", 1]}}},
        {"agents.claude.extra_args.1": [f.Type.CODE_WRONG_TYPE]},
        skip_value_check,
    )


def test_agents_rejects_an_unknown_setting(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """Without server_settings, extra_args is the only setting."""
    assert_filter_errors(
        _per_source_schema(),
        {"agents": {"claude": {"server": {}}}},
        {"agents.claude.server": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_agents_rejects_a_non_table(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """agents must be a table keyed by agent name."""
    assert_filter_errors(
        _per_source_schema(),
        {"agents": "claude"},
        {"agents": [f.Type.CODE_WRONG_TYPE]},
        skip_value_check,
    )


def test_project_entry_accepts_agents(
    assert_filter_passes: Callable[..., FilterRunner], tmp_path: Path
) -> None:
    """A [projects] entry may carry agents settings."""
    assert_filter_passes(
        user_config_schema(base_dir=tmp_path),
        '[projects."/x".agents.claude]\nextra_args = ["--resume"]\n',
        skip_value_check,
    )


def test_agents_normalises_extra_args_as_unicode(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """Each argument passes through f.Unicode, as config strings do."""
    assert_filter_passes(
        _per_source_schema(),
        {"agents": {"claude": {"extra_args": ["café"]}}},
        {"agents": {"claude": {"extra_args": ["café"]}}},
    )


def test_agent_rejects_an_empty_table(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """An agent table naming neither half is empty, and so missing."""
    assert_filter_errors(
        standard_config_schema(base_dir=Path.cwd(), merged=True),
        {"image": "i", "agent": {}},
        {"agent": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def _server_schema():
    """The per-source schema as the user config's global section sees it."""
    return standard_config_schema(
        base_dir=Path.cwd(), merged=False, server_settings=True
    )


def _server(settings: dict) -> dict:
    """Wrap server settings as config for a server named ``x``."""
    return {"agents": {"x": {"server": settings}}}


def test_server_settings_accept_every_key(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """image, port, volumes and build are the server settings."""
    assert_filter_passes(
        _server_schema(),
        _server(
            {
                "build": {"dockerfile": "/abs/Dockerfile", "policy": "daily"},
                "image": "img",
                "port": 4096,
                "volumes": {"/abs": "/abs:rw"},
            }
        ),
        _server(
            {
                "build": {"dockerfile": "/abs/Dockerfile", "policy": "daily"},
                "image": "img",
                "port": 4096,
                "volumes": {"/abs": VolumeSpec("/abs", "rw")},
            }
        ),
    )


def test_server_settings_reject_a_relative_volume(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """A shared server's mounts cannot depend on the workdir (ADR 019)."""
    assert_filter_errors(
        _server_schema(),
        _server({"volumes": {"rel/dir": "/c:rw"}}),
        {"agents.x.server.volumes.rel/dir": [AbsoluteHostPath.CODE_NOT_ABSOLUTE]},
        skip_value_check,
    )


def test_server_settings_accept_a_tilde_volume(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """A leading ``~`` is home, so the path is absolute once expanded."""
    assert_filter_passes(
        _server_schema(), _server({"volumes": {"~/Dev": "~/Dev:rw"}}), skip_value_check
    )


def test_server_settings_reject_another_users_home(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """``~`` means home only as a whole first segment, as Filepath has it."""
    assert_filter_errors(
        _server_schema(),
        _server({"volumes": {"~bob/Dev": "/c:rw"}}),
        {"agents.x.server.volumes.~bob/Dev": [AbsoluteHostPath.CODE_NOT_ABSOLUTE]},
        skip_value_check,
    )


def test_server_settings_reject_a_relative_build_path(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """The build's dockerfile and context must be absolute too."""
    assert_filter_errors(
        _server_schema(),
        _server({"build": {"dockerfile": "Dockerfile"}}),
        {"agents.x.server.build.dockerfile": [AbsoluteHostPath.CODE_NOT_ABSOLUTE]},
        skip_value_check,
    )
    assert_filter_errors(
        _server_schema(),
        _server({"build": {"context": "ctx"}}),
        {"agents.x.server.build.context": [AbsoluteHostPath.CODE_NOT_ABSOLUTE]},
        skip_value_check,
    )


def test_server_settings_reject_a_bad_port(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """A port is an integer from 1 to 65535, and nothing is converted to one."""
    for port, code in (
        (0, f.Min.CODE_TOO_SMALL),
        (65536, f.Max.CODE_TOO_BIG),
        ("4096", f.Type.CODE_WRONG_TYPE),
        (True, f.Type.CODE_WRONG_TYPE),
    ):
        assert_filter_errors(
            _server_schema(),
            _server({"port": port}),
            {"agents.x.server.port": [code]},
            skip_value_check,
        )


def test_server_settings_reject_an_unknown_key(
    assert_filter_errors: Callable[..., FilterRunner],
) -> None:
    """A misspelt server setting is an error."""
    assert_filter_errors(
        _server_schema(),
        _server({"imge": "i"}),
        {"agents.x.server.imge": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_server_settings_do_not_touch_disk(
    assert_filter_passes: Callable[..., FilterRunner],
) -> None:
    """Paths are checked on disk only when that server is chosen (ADR 019)."""
    assert_filter_passes(
        _server_schema(),
        _server(
            {
                "build": {"context": "/no/such", "dockerfile": "/no/such/Dockerfile"},
                "volumes": {"/no/such/dir": "/no/such/dir:rw"},
            }
        ),
        skip_value_check,
    )


def test_projects_entry_rejects_server_settings(tmp_path: Path) -> None:
    """A shared server has no per-project settings (ADR 019)."""
    runner = f.FilterRunner(
        user_config_schema(base_dir=tmp_path),
        '[projects."/x".agents.y.server]\nimage = "i"\n',
    )
    assert not runner.is_valid()
    assert [key for key in runner.errors if key.endswith("agents.y.server")]


def test_user_global_section_accepts_server_settings(
    assert_filter_passes: Callable[..., FilterRunner], tmp_path: Path
) -> None:
    """Server settings belong in the user config's global section."""
    assert_filter_passes(
        user_config_schema(base_dir=tmp_path),
        '[agents.y.server]\nimage = "i"\n',
        skip_value_check,
    )
