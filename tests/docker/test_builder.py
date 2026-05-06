from pathlib import Path
from unittest.mock import MagicMock


from paddock.docker.builder import DockerCommandBuilder, sanitise_volume_name


def test_sanitise_volume_name():
    assert (
        sanitise_volume_name("ubuntu:22.04", "claude") == "paddock_ubuntu_22_04_claude"
    )
    assert (
        sanitise_volume_name("my.registry/image:tag", "false")
        == "paddock_my_registry_image_tag_false"
    )


def make_agent(command=None, volumes=None, scratch_volumes=None):
    agent = MagicMock()
    agent.AGENT_KEY = "claude"
    agent.get_command.return_value = command or ["claude"]
    agent.get_volumes.return_value = volumes or {}
    agent.get_scratch_volumes.return_value = scratch_volumes or {}
    return agent


def test_minimal_command(mocker, tmp_path: Path):
    """
    A minimal docker run command includes:
    - 'docker run' to invoke docker
    - '--rm' to remove the container on exit (no cleanup needed)
    - '-it' for interactive TTY (required for coding agents)
    - '--name' set to the paddock-{dirname}-{agent} convention
    - '--workdir' set to the same absolute path as the host workdir
    - '-v {workdir}:{workdir}:rw' to mount the workdir at the same path
    - the image name
    """
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent()
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    assert argv[0] == "docker"
    assert "run" in argv
    assert "--rm" in argv
    assert "-it" in argv
    assert f"--workdir={tmp_path}" in argv
    assert "-v" in argv
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert any(f"{tmp_path}:{tmp_path}:rw" in v for v in vol_args)
    assert "ubuntu:22.04" in argv


def test_container_name_from_workdir(mocker, tmp_path: Path):
    """Container is named 'paddock-{dirname}-{agent}'."""
    workdir = tmp_path / "my-project"
    workdir.mkdir()
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent()
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=workdir).build(
        command=[]
    )
    assert "--name" in argv
    name_idx = argv.index("--name")
    assert argv[name_idx + 1] == "paddock-my-project-claude"


def test_container_name_suffix_on_conflict(mocker, tmp_path: Path):
    """If the container name is taken, a numeric suffix is appended."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent()
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        side_effect=[False, True],
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    name_idx = argv.index("--name")
    assert argv[name_idx + 1].endswith("-1")


def test_uses_agent_command(mocker, tmp_path: Path):
    """When no command override is given, the agent's default command is appended."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent(command=["claude"])
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    assert argv[-1] == "claude"


def test_command_override(mocker, tmp_path: Path):
    """An explicit command overrides the agent default."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent(command=["claude"])
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=["opencode", "--flag"]
    )
    assert argv[-2:] == ["opencode", "--flag"]


def test_config_volumes(mocker, tmp_path: Path):
    """Config volumes are passed as -v flags."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {"/host/data": "/data:ro"},
        "network": None,
    }
    agent = make_agent()
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert any("/host/data:/data:ro" in v for v in vol_args)


def test_network(mocker, tmp_path: Path):
    """A configured network is passed via --network."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": "mynet",
    }
    agent = make_agent()
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    assert "--network" in argv
    assert "mynet" in argv


def test_scratch_volume(mocker, tmp_path: Path):
    """Agent scratch volumes (named Docker volumes) are passed via -v."""
    config = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent(scratch_volumes={"paddock_ubuntu_22_04_claude": "/scratch"})
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert any("paddock_ubuntu_22_04_claude:/scratch" in v for v in vol_args)
