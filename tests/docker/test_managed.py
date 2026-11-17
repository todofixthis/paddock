import json

import pytest

from paddock.config.errors import PaddockEnvironmentError
from paddock.agents.servers import Secret
from paddock.config.filters import VolumeSpec
from paddock.docker.environment import ContainerEnvironment
from paddock.docker.managed import (
    ContainerSpec,
    ContainerState,
    ManagedContainer,
)

VOLUMES = [("/host/a", VolumeSpec("/a", "rw")), ("state", VolumeSpec("/state", "rw"))]


def _spec(**overrides) -> ContainerSpec:
    """A spec for container ``n`` owned by ``server:srv``."""
    values: dict = {
        "name": "n",
        "owner": "server:srv",
        "image": "img",
        "command": ["serve", "--now"],
        "env": {"MODE": "fast", "TOKEN": Secret("s3cr3t")},
        "volumes": VOLUMES,
        "container_port": 1234,
        "host_port": None,
    }
    values.update(overrides)
    values["env"] = ContainerEnvironment(values["env"])
    return ContainerSpec(**values)


def test_run_argv_shape():
    spec = _spec()
    volumes = json.dumps([["/host/a", "/a:rw"], ["state", "/state:rw"]])
    assert spec.run_argv() == [
        "docker",
        "run",
        "-d",
        "--name",
        "n",
        "--network",
        "n",
        "--label",
        "paddock.managed=server:srv",
        "--label",
        f"paddock.spec-hash={spec.spec_hash()}",
        "--label",
        f"paddock.volumes={volumes}",
        "-p",
        "127.0.0.1::1234",
        "-e",
        "MODE=fast",
        "-e",
        "TOKEN",
        "-v",
        "/host/a:/a:rw",
        "-v",
        "state:/state:rw",
        "img",
        "serve",
        "--now",
    ]


def test_run_argv_with_a_host_port():
    argv = _spec(host_port=4096).run_argv()
    assert argv[argv.index("-p") + 1] == "127.0.0.1:4096:1234"


def test_run_argv_sorts_env_names():
    argv = _spec(env={"B": Secret("1"), "A": "2"}).run_argv()
    assert [argv[i + 1] for i, a in enumerate(argv) if a == "-e"] == ["A=2", "B"]


def test_run_argv_never_holds_a_secret_env_value():
    spec = _spec()
    assert not any("s3cr3t" in arg for arg in spec.run_argv())
    assert "s3cr3t" not in repr(spec)


def test_spec_hash_ignores_a_secret_value_but_not_its_name():
    base = _spec(env={"TOKEN": Secret("x")}).spec_hash()
    assert _spec(env={"TOKEN": Secret("other")}).spec_hash() == base
    assert _spec(env={"OTHER": Secret("x")}).spec_hash() != base


def test_spec_hash_changes_with_a_safe_env_value():
    base = _spec(env={"MODE": "fast"}).spec_hash()
    assert _spec(env={"MODE": "slow"}).spec_hash() != base
    assert _spec(env={"MODE": Secret("fast")}).spec_hash() != base


def test_spec_hash_changes_with_image_command_volumes_and_ports():
    base = _spec().spec_hash()
    assert _spec(image="other").spec_hash() != base
    assert _spec(command=["serve"]).spec_hash() != base
    assert _spec(volumes=VOLUMES[:1]).spec_hash() != base
    assert _spec(container_port=1).spec_hash() != base
    assert _spec(host_port=4096).spec_hash() != base


def test_spec_hash_ignores_volume_order():
    assert _spec(volumes=VOLUMES[::-1]).spec_hash() == _spec().spec_hash()


def test_status_missing(docker):
    status = ManagedContainer(_spec()).status()
    assert status.state is ContainerState.MISSING
    assert status.container_id is None


def test_status_running(docker):
    docker.container = docker.container_entry()
    status = ManagedContainer(_spec()).status()
    assert status.state is ContainerState.RUNNING
    assert status.container_id == "abc123"


def test_status_stopped(docker):
    docker.container = docker.container_entry(status="exited")
    assert ManagedContainer(_spec()).status().state is ContainerState.STOPPED


def test_status_created_is_starting(docker):
    docker.container = docker.container_entry(status="created")
    assert ManagedContainer(_spec()).status().state is ContainerState.STARTING


def test_status_created_with_an_error_is_stopped(docker):
    docker.container = docker.container_entry(status="created", error="exec: not found")
    assert ManagedContainer(_spec()).status().state is ContainerState.STOPPED


def test_status_foreign_without_the_label(docker):
    docker.container = docker.container_entry(owner=None)
    assert ManagedContainer(_spec()).status().state is ContainerState.FOREIGN


def test_status_foreign_with_another_owner(docker):
    docker.container = docker.container_entry(owner="server:other")
    assert ManagedContainer(_spec()).status().state is ContainerState.FOREIGN


def test_status_exposes_env_and_labels(docker):
    docker.container = docker.container_entry(
        env=["TOKEN=s3=cr3t", "BARE"], labels={"x": "y"}
    )
    status = ManagedContainer(_spec()).status()
    assert status.env == {"TOKEN": "s3=cr3t", "BARE": ""}
    assert status.labels == {"paddock.managed": "server:srv", "x": "y"}
    assert "s3=cr3t" not in repr(status)


def test_status_asks_for_a_container_not_any_object(docker):
    ManagedContainer(_spec()).status()
    assert docker.calls == [["docker", "container", "inspect", "n"]]


def test_start_creates_the_network_then_runs(docker):
    spec = _spec()
    assert ManagedContainer(spec).start() is True
    assert docker.calls == [
        ["docker", "network", "inspect", "n"],
        ["docker", "network", "create", "--label", "paddock.managed=server:srv", "n"],
        spec.run_argv(),
    ]


def test_start_reuses_an_owned_network(docker):
    docker.network = docker.network_entry()
    ManagedContainer(_spec()).start()
    assert docker.ran("docker", "network", "create") == []
    assert len(docker.ran("docker", "run")) == 1


def test_start_refuses_a_foreign_network(docker):
    docker.network = docker.network_entry(owner=None)
    with pytest.raises(PaddockEnvironmentError) as exc:
        ManagedContainer(_spec()).start()
    assert str(exc.value) == (
        '[docker] A network named "n" exists that paddock did not create; '
        "remove or rename it"
    )
    assert docker.ran("docker", "run") == []


def test_a_network_owned_by_another_server_is_foreign(docker):
    docker.network = docker.network_entry(owner="server:other")
    with pytest.raises(PaddockEnvironmentError):
        ManagedContainer(_spec()).check_network()


def test_check_network_creates_nothing_when_missing(docker):
    ManagedContainer(_spec()).check_network()
    assert docker.calls == [["docker", "network", "inspect", "n"]]


def test_check_network_creates_nothing_when_owned(docker):
    docker.network = docker.network_entry()
    ManagedContainer(_spec()).check_network()
    assert docker.calls == [["docker", "network", "inspect", "n"]]


def test_start_tolerates_a_network_create_race(docker):
    docker.network_create_returncode = 1
    docker.network_after_failed_create = docker.network_entry()
    assert ManagedContainer(_spec()).start() is True
    assert len(docker.ran("docker", "run")) == 1


def test_start_reports_a_network_it_could_not_create(docker):
    docker.network_create_returncode = 1
    with pytest.raises(PaddockEnvironmentError) as exc:
        ManagedContainer(_spec()).start()
    assert str(exc.value) == '[docker] Could not start "n": Error: network exists'
    assert docker.ran("docker", "run") == []


def test_start_passes_env_values_in_the_environment(docker, monkeypatch):
    monkeypatch.setenv("PATH_MARKER", "kept")
    ManagedContainer(_spec()).start()
    env = docker.env_of("docker", "run")
    assert env["TOKEN"] == "s3cr3t"
    assert "MODE" not in env
    assert env["PATH_MARKER"] == "kept"


def test_start_tolerates_a_name_conflict(docker):
    docker.run_returncode = 125
    docker.run_stderr = (
        "docker: Error response from daemon: Conflict. The container name "
        '"/n" is already in use by container "abc".\n'
    )
    assert ManagedContainer(_spec()).start() is False


def test_a_port_conflict_is_not_a_name_conflict(docker):
    docker.run_returncode = 125
    docker.run_stderr = (
        "docker: Error response from daemon: failed to bind host port for "
        "127.0.0.1:4096: address already in use\n"
    )
    with pytest.raises(PaddockEnvironmentError) as exc:
        ManagedContainer(_spec()).start()
    assert str(exc.value).startswith('[docker] Could not start "n": ')


def test_start_reports_other_failures(docker):
    docker.run_returncode = 125
    docker.run_stderr = (
        "\ndocker: Error response from daemon: no such image\n"
        "Run 'docker run --help' for more information\n"
    )
    with pytest.raises(PaddockEnvironmentError) as exc:
        ManagedContainer(_spec()).start()
    assert str(exc.value) == (
        '[docker] Could not start "n": docker: Error response from daemon: '
        "no such image"
    )


def test_remove_stopped_uses_the_id_and_no_force(docker):
    docker.container = docker.container_entry(status="exited", container_id="dead1")
    ManagedContainer(_spec()).remove_stopped("dead1")
    assert docker.calls == [["docker", "rm", "dead1"]]


def test_remove_stopped_ignores_failure(docker):
    docker.rm_returncode = 1
    ManagedContainer(_spec()).remove_stopped("gone")


def test_published_port_parses_docker_port(docker):
    docker.container = docker.container_entry()
    assert ManagedContainer(_spec()).published_port() == 32768
    assert docker.calls == [["docker", "port", "n", "1234/tcp"]]


def test_published_port_is_none_when_unpublished(docker):
    assert ManagedContainer(_spec()).published_port() is None


def test_volumes_round_trip_through_labels(docker):
    container = ManagedContainer(_spec(volumes=VOLUMES[::-1]))
    container.start()
    assert ManagedContainer.volumes_from_labels(container.status().labels) == VOLUMES
    assert docker.container is not None


def test_volumes_from_labels_without_the_label_is_empty():
    assert ManagedContainer.volumes_from_labels({}) == []


def test_start_reports_the_daemons_error_not_the_pull_preamble(docker):
    """A missing local image puts a notice ahead of the reason on stderr."""
    docker.run_returncode = 125
    docker.run_stderr = (
        "Unable to find image 'x:1' locally\n"
        "docker: Error response from daemon: pull access denied for x\n"
        "Run 'docker run --help' for more information\n"
    )
    with pytest.raises(PaddockEnvironmentError) as exc:
        ManagedContainer(_spec()).start()
    assert str(exc.value) == (
        '[docker] Could not start "n": docker: Error response from daemon: '
        "pull access denied for x"
    )
