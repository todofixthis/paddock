import filters as f
import pytest
from filters.pytest import skip_value_check

from paddock.config.filters import VolumeSpec
from paddock.config.schema import (
    ConfigSchema,
    config_meta_schema,
    standard_config_schema,
    user_config_schema,
)


def test_valid_minimal():
    """Minimal valid config passes; absent optional fields are stripped by DropEmpty."""
    result = ConfigSchema().validate({"image": "ubuntu:22.04", "agent": "claude"})
    assert result["image"] == "ubuntu:22.04"
    assert result["agent"] == "claude"


def test_invalid_empty_image():
    """An empty string is not a valid image name."""
    with pytest.raises(SystemExit):
        ConfigSchema().validate({"image": "", "agent": "claude"})


def test_invalid_missing_image():
    """image is required — omitting it should fail."""
    with pytest.raises(SystemExit):
        ConfigSchema().validate({"agent": "claude"})


def test_agent_false():
    """agent = False (bool) enables shell mode."""
    result = ConfigSchema().validate({"image": "ubuntu:22.04", "agent": False})
    assert result["agent"] is False


def test_unknown_key_rejected():
    """Unknown config keys indicate a typo and should be rejected."""
    with pytest.raises(SystemExit):
        ConfigSchema().validate(
            {"image": "ubuntu:22.04", "agent": "claude", "typo": "oops"}
        )


def test_valid_build_config(tmp_path):
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
    result = ConfigSchema().validate(config)
    assert result["build"]["policy"] == "if-missing"


def test_valid_build_args(tmp_path):
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
    result = ConfigSchema().validate(config)
    assert result["build"]["args"] == {"FOO": "bar", "PYTHON_VERSION": "3.13"}


def test_valid_volumes(tmp_path):
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
    result = ConfigSchema().validate(config)
    assert result["volumes"][str(implicit.resolve())] == VolumeSpec(
        "/container/implicit", "ro"
    )
    assert result["volumes"][str(explicit_ro.resolve())] == VolumeSpec(
        "/container/ro", "ro"
    )
    assert result["volumes"][str(explicit_rw.resolve())] == VolumeSpec(
        "/container/rw", "rw"
    )


def test_invalid_volume_value():
    """A volume destination with more than one colon segment is invalid."""
    with pytest.raises(SystemExit):
        ConfigSchema().validate(
            {
                "image": "ubuntu:22.04",
                "agent": "claude",
                "volumes": {"/host": "not:a:valid:path"},
            }
        )


def test_build_dockerfile_tilde_expanded(monkeypatch, tmp_path):
    """'~/Dockerfile' is expanded using Path.home()."""
    monkeypatch.setenv("HOME", str(tmp_path))
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": "~/Dockerfile"},
        "image": "myimage",
    }
    result = f.FilterRunner(standard_config_schema(merged=True), raw)
    assert result.is_valid()
    assert not str(result.cleaned_data["build"]["dockerfile"]).startswith("~")


def test_build_context_tilde_expanded(monkeypatch, tmp_path):
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
    result = f.FilterRunner(standard_config_schema(merged=True), raw)
    assert result.is_valid()
    assert not str(result.cleaned_data["build"]["context"]).startswith("~")


def test_build_context_none_unchanged(tmp_path):
    """None context is stripped by DropEmpty; the build section remains valid."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": str(dockerfile), "context": None},
        "image": "myimage",
    }
    result = f.FilterRunner(standard_config_schema(merged=True), raw)
    assert result.is_valid()
    assert result.cleaned_data["build"].get("context") is None


def test_standard_schema_non_merged_accepts_minimal(assert_filter_passes):
    """In per-source mode the schema accepts arbitrarily incomplete configs."""
    assert_filter_passes(
        standard_config_schema(merged=False),
        {"image": "ubuntu:22.04"},
        skip_value_check,
    )


def test_standard_schema_non_merged_accepts_empty(assert_filter_passes):
    """Per-source mode allows an entirely empty dict — sources may contribute nothing."""
    assert_filter_passes(standard_config_schema(merged=False), {}, skip_value_check)


def test_standard_schema_merged_requires_image(assert_filter_errors):
    """In merged mode ``image`` is required."""
    assert_filter_errors(
        standard_config_schema(merged=True),
        {"agent": "claude"},
        {"image": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_standard_schema_merged_requires_agent(assert_filter_errors):
    """In merged mode ``agent`` is required."""
    assert_filter_errors(
        standard_config_schema(merged=True),
        {"image": "x"},
        {"agent": [f.NotEmpty.CODE_EMPTY]},
        skip_value_check,
    )


def test_standard_schema_rejects_unknown_top_level_key(assert_filter_errors):
    """Unknown top-level keys indicate a typo and should be rejected."""
    assert_filter_errors(
        standard_config_schema(merged=False),
        {"image": "x", "wat": "no"},
        {"wat": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_standard_schema_with_extra_keys_macro(assert_filter_passes):
    """``extra_keys`` allows additional top-level keys such as ``config``."""
    schema = standard_config_schema(
        extra_keys={"config": config_meta_schema}, merged=False
    )
    assert_filter_passes(
        schema,
        {"image": "x", "config": {"allowlist": {"project_toml": True}}},
        skip_value_check,
    )


def test_user_config_schema_accepts_projects_and_config(assert_filter_passes):
    """user_config_schema accepts projects and config sections."""
    assert_filter_passes(
        user_config_schema,
        'image = "base:1.0"\nagent = "claude"\n'
        '[projects."/abs/path"]\nimage = "p:2"\n'
        "[config.allowlist]\nproject_toml = true\n",
        skip_value_check,
    )


def test_user_config_schema_rejects_unknown_allowlist_source(assert_filter_errors):
    """Unknown allowlist source keys are rejected."""
    assert_filter_errors(
        user_config_schema,
        'agent = "claude"\nimage = "x"\n[config.allowlist]\nfoo = true\n',
        {"config.allowlist.foo": [f.FilterMapper.CODE_EXTRA_KEY]},
        skip_value_check,
    )


def test_allowlist_entry_accepts_true(assert_filter_passes):
    """AllowlistEntry accepts the boolean ``True``."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_passes(AllowlistEntry, True, True)


def test_allowlist_entry_accepts_known_dotted_paths(assert_filter_passes):
    """AllowlistEntry accepts a list of known dotted paths."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_passes(
        AllowlistEntry, ["image", "build.dockerfile"], skip_value_check
    )


def test_allowlist_entry_rejects_unknown_dotted_path(assert_filter_errors):
    """AllowlistEntry rejects unknown dotted paths."""
    from paddock.config.filters import AllowlistEntry

    assert_filter_errors(
        AllowlistEntry, ["bogus"], {"0": [f.Choice.CODE_INVALID]}, skip_value_check
    )
