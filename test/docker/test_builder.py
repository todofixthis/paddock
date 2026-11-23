from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from paddock.agents.servers import Secret, ServerConnection
from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec
from paddock.docker.builder import DockerCommandBuilder, sanitise_volume_name


def test_sanitise_volume_name() -> None:
    assert (
        sanitise_volume_name("ubuntu:22.04", "claude") == "paddock_ubuntu_22_04_claude"
    )
    assert (
        sanitise_volume_name("my.registry/image:tag", "false")
        == "paddock_my_registry_image_tag_false"
    )


def make_agent(
    command=None,
    volumes=None,
    scratch_volumes=None,
    server_args=None,
    server_env=None,
):
    agent = MagicMock()
    agent.AGENT_KEY = "claude"
    agent.get_command.return_value = command or ["claude"]
    agent.get_volumes.return_value = volumes or {}
    agent.get_scratch_volumes.return_value = scratch_volumes or {}
    agent.get_server_args.return_value = server_args or []
    agent.get_server_env.return_value = server_env or {}
    return agent


def test_minimal_command(mocker: MockerFixture, tmp_path: Path) -> None:
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
    config: dict[str, object] = {
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


def test_container_name_from_workdir(mocker: MockerFixture, tmp_path: Path) -> None:
    """Container is named 'paddock-{dirname}-{agent}'."""
    workdir = tmp_path / "my-project"
    workdir.mkdir()
    config: dict[str, object] = {
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


def test_container_name_suffix_on_conflict(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """If the container name is taken, a numeric suffix is appended."""
    config: dict[str, object] = {
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


def test_uses_agent_command(mocker: MockerFixture, tmp_path: Path) -> None:
    """When no command override is given, the agent's default command is appended."""
    config: dict[str, object] = {
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


def test_command_override(mocker: MockerFixture, tmp_path: Path) -> None:
    """An explicit command overrides the agent default."""
    config: dict[str, object] = {
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


def test_agent_args_extend_agent_command(mocker: MockerFixture, tmp_path: Path) -> None:
    """Agent args are appended to the agent's default command."""
    config: dict[str, object] = {
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
        command=[], agent_args=["fix this bug"]
    )
    assert argv[-3:] == ["ubuntu:22.04", "claude", "fix this bug"]


def test_config_volumes(mocker: MockerFixture, tmp_path: Path) -> None:
    """Config volumes are passed as -v flags."""
    config: dict[str, object] = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {"/host/data": VolumeSpec("/data", "ro")},
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


def test_network(mocker: MockerFixture, tmp_path: Path) -> None:
    """A configured network is passed via --network."""
    config: dict[str, object] = {
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


def test_scratch_volume(mocker: MockerFixture, tmp_path: Path) -> None:
    """Agent scratch volumes (named Docker volumes) are passed via -v."""
    config: dict[str, object] = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent(
        scratch_volumes={"paddock_ubuntu_22_04_claude": VolumeSpec("/scratch", "rw")}
    )
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(
        command=[]
    )
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert any("paddock_ubuntu_22_04_claude:/scratch:rw" in v for v in vol_args)


def test_project_dir_volume_added_after_workdir(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    config: dict[str, object] = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    pd = tmp_path / ".paddock"
    pd.mkdir()
    argv = DockerCommandBuilder(
        config=config,
        agent=make_agent(),
        workdir=tmp_path,
        project_dir_volume=(str(pd), VolumeSpec(str(pd), "ro")),
    ).build(command=[])
    vols = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    workdir_i = next(i for i, v in enumerate(vols) if f"{tmp_path}:{tmp_path}:rw" in v)
    paddock_i = next(i for i, v in enumerate(vols) if str(pd) in v and "ro" in v)
    assert paddock_i > workdir_i


def test_no_project_dir_volume_when_none(mocker: MockerFixture, tmp_path: Path) -> None:
    config: dict[str, object] = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    argv = DockerCommandBuilder(
        config=config,
        agent=make_agent(),
        workdir=tmp_path,
        project_dir_volume=None,
    ).build(command=[])
    vols = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert not any(".paddock" in v for v in vols)


def test_volumes_snapshot_shared_with_build(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    """``build()`` reuses the volumes already read, not a fresh probe.

    Agent volumes probe the filesystem, and an image build can run between
    the "Mounting" log and ``build()``; both must report the same mounts.
    """
    config: dict[str, object] = {
        "image": "ubuntu:22.04",
        "agent": "claude",
        "volumes": {},
        "network": None,
    }
    agent = make_agent()
    agent.get_volumes.side_effect = [
        {"/host/.claude.json": VolumeSpec("/root/.claude.json", "rw")},
        {},
    ]
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    builder = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path)
    logged = builder.volumes
    argv = builder.build(command=[])
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == "-v"]
    assert vol_args == [f"{host}:{spec}" for host, spec in logged]
    assert "/host/.claude.json:/root/.claude.json:rw" in vol_args


CONNECTION = ServerConnection(
    container_url="http://paddock-server-srv:1234",
    host_url="http://127.0.0.1:32768",
    network="paddock-server-srv",
    secret="s3cr3t",
)


def _paired_builder(
    mocker, tmp_path: Path, *, network=None, agent=None, connection=CONNECTION
):
    """A builder for a client, paired with ``connection`` unless it is None."""
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    return DockerCommandBuilder(
        config={"image": "img", "volumes": {}, "network": network},
        agent=agent or make_agent(),
        workdir=tmp_path,
        connection=connection,
    )


def _networks(argv: list[str]) -> list[str]:
    """Every ``--network`` value in ``argv``."""
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--network"]


def test_paired_client_joins_the_servers_network(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    argv = _paired_builder(mocker, tmp_path).build(command=[])
    assert _networks(argv) == ["paddock-server-srv"]


def test_paired_client_keeps_its_configured_network_too(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    argv = _paired_builder(mocker, tmp_path, network="mine").build(command=[])
    assert _networks(argv) == ["mine", "paddock-server-srv"]


def test_configured_network_equal_to_the_servers_is_passed_once(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    builder = _paired_builder(mocker, tmp_path, network="paddock-server-srv")
    assert _networks(builder.build(command=[])) == ["paddock-server-srv"]


def test_server_env_shows_safe_values_and_hides_secret_ones(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    agent = make_agent(
        server_env={
            "OPENCODE_PASSWORD": CONNECTION.secret,
            "A_URL": "u",
            "DERIVED": Secret("dXNlcjpwdw=="),
        }
    )
    builder = _paired_builder(mocker, tmp_path, agent=agent)
    argv = builder.build(command=[])
    flags = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "-e"]
    assert flags == ["A_URL=u", "DERIVED", "OPENCODE_PASSWORD"]
    assert argv.index("-e") < argv.index("img")
    assert not any(CONNECTION.secret in arg for arg in argv)
    assert not any("dXNlcjpwdw==" in arg for arg in argv)
    assert builder.environment.secrets == {
        "DERIVED": "dXNlcjpwdw==",
        "OPENCODE_PASSWORD": CONNECTION.secret,
    }
    agent.get_server_env.assert_called_with(CONNECTION)


def test_server_args_precede_agent_args(mocker: MockerFixture, tmp_path: Path) -> None:
    agent = make_agent(server_args=["--server", "http://x"])
    argv = _paired_builder(mocker, tmp_path, agent=agent).build(
        command=[], agent_args=["extra", "cli"]
    )
    assert argv[-5:] == ["claude", "--server", "http://x", "extra", "cli"]
    agent.get_server_args.assert_called_with(CONNECTION)


def test_replacement_command_drops_server_args(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    agent = make_agent(server_args=["--server", "http://x"])
    argv = _paired_builder(mocker, tmp_path, agent=agent).build(command=["bash"])
    assert argv[-2:] == ["img", "bash"]


def test_unpaired_client_is_untouched(mocker: MockerFixture, tmp_path: Path) -> None:
    agent = make_agent(server_args=["--server", "x"], server_env={"P": "v"})
    builder = _paired_builder(mocker, tmp_path, agent=agent, connection=None)
    argv = builder.build(command=[], agent_args=["extra"])
    assert "--network" not in argv
    assert "-e" not in argv
    assert argv[-3:] == ["img", "claude", "extra"]
    assert builder.environment.secrets == {}


@pytest.mark.parametrize(
    "network", ["host", "none", "bridge", "default", "container:abc"]
)
def test_paired_network_check_refuses_uncombinable_networks(network: str) -> None:
    with pytest.raises(PaddockEnvironmentError) as exc:
        DockerCommandBuilder.check_paired_network(
            network, agent_key="paired", server_key="srv"
        )
    assert str(exc.value) == (
        f'[network] "{network}" cannot be combined with a server\'s network; '
        'agent "paired" is paired with server "srv"'
    )


@pytest.mark.parametrize("network", [None, "mine", "hosting"])
def test_paired_network_check_allows_a_user_network_or_none(
    network: str | None,
) -> None:
    DockerCommandBuilder.check_paired_network(
        network, agent_key="paired", server_key="srv"
    )
