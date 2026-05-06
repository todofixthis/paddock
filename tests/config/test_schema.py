import pytest

from paddock.config.schema import ConfigSchema


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


def test_valid_build_config():
    """build config with all fields valid."""
    config = {
        "image": "myapp:latest",
        "agent": "claude",
        "build": {
            "dockerfile": "/path/to/Dockerfile",
            "context": None,
            "policy": "if-missing",
        },
    }
    result = ConfigSchema().validate(config)
    assert result["build"]["policy"] == "if-missing"


def test_valid_build_args():
    """build.args accepts arbitrary key-value pairs (user-defined Dockerfile ARGs)."""
    config = {
        "image": "myapp:latest",
        "agent": "claude",
        "build": {
            "dockerfile": "/Dockerfile",
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
