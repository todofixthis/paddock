import filters as f
import pytest

from paddock.config.schema import ConfigSchema, _config_schema


def test_valid_minimal():
    """Minimal valid config resolves with defaults filled in."""
    result = ConfigSchema().validate({"image": "ubuntu:22.04", "agent": "claude"})
    assert result == {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "build": None,
        "volumes": {},
        "network": None,
    }


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


def test_valid_volumes():
    """
    Volumes can be specified as a bare path (implicit :ro), explicit :ro, or explicit :rw.
    The Volume filter normalises bare paths by appending ':ro'.
    """
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {
            # Implicit :ro — Volume filter appends ':ro'
            "/implicit": "/container/implicit",
            # Explicit :ro
            "/explicit-ro": "/container/ro:ro",
            # Explicit :rw
            "/explicit-rw": "/container/rw:rw",
        },
    }
    result = ConfigSchema().validate(config)
    assert result["volumes"]["/implicit"] == "/container/implicit:ro"
    assert result["volumes"]["/explicit-ro"] == "/container/ro:ro"
    assert result["volumes"]["/explicit-rw"] == "/container/rw:rw"


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
        "network": None,
        "volumes": {},
    }
    result = f.FilterRunner(_config_schema, raw)
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
        "network": None,
        "volumes": {},
    }
    result = f.FilterRunner(_config_schema, raw)
    assert result.is_valid()
    assert not str(result.cleaned_data["build"]["context"]).startswith("~")


def test_build_context_none_unchanged(tmp_path):
    """None context passes through the filepath filter unchanged."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("")
    raw = {
        "agent": "claude",
        "build": {"dockerfile": str(dockerfile), "context": None},
        "image": "myimage",
        "network": None,
        "volumes": {},
    }
    result = f.FilterRunner(_config_schema, raw)
    assert result.is_valid()
    assert result.cleaned_data["build"]["context"] is None
