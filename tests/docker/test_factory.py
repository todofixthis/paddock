from pathlib import Path

from paddock.docker.build import ImageBuilder
from paddock.docker.factory import ImageSourceFactory
from paddock.docker.pull import ImagePuller
from paddock.docker.source import BuildPolicy


def test_dockerfile_builds():
    source = ImageSourceFactory.from_config(
        {
            "args": {"AGENT": "none", "NODE_VERSION": "24"},
            "dockerfile": Path("/src/images/Dockerfile"),
            "policy": "daily",
        },
        agent_build_args={"AGENT": "claude"},
        environ={},
    )
    assert isinstance(source, ImageBuilder)
    assert source.policy is BuildPolicy.DAILY
    assert source.context == Path("/src/images")
    assert source.build_args == {"AGENT": "none", "NODE_VERSION": "24"}


def test_build_context_overrides_dockerfile_directory():
    source = ImageSourceFactory.from_config(
        {"context": Path("/src"), "dockerfile": Path("/src/images/Dockerfile")},
        agent_build_args={},
        environ={},
    )
    assert isinstance(source, ImageBuilder)
    assert source.context == Path("/src")


def test_no_dockerfile_pulls(tmp_path):
    source = ImageSourceFactory.from_config(
        {"policy": "weekly"},
        agent_build_args={"AGENT": "claude"},
        environ={"XDG_STATE_HOME": str(tmp_path)},
    )
    assert isinstance(source, ImagePuller)
    assert source.policy is BuildPolicy.WEEKLY
    assert source.log.path == tmp_path / "paddock" / "pulls.json"


def test_policy_defaults_to_if_missing():
    source = ImageSourceFactory.from_config(
        {"args": {"FOO": "bar"}}, agent_build_args={}, environ={}
    )
    assert source.policy is BuildPolicy.IF_MISSING
