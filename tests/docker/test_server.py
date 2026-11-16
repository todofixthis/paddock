import logging
import subprocess
from pathlib import Path

import pytest

from paddock.agents.servers import BaseServer, ServerConnection
from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec
from paddock.config.server_settings import ServerSettings
from paddock.docker.server import SECRET_ENV, LaunchResult, ServerLauncher

NAME = "paddock-server-srv"
RW_A = {"/a": VolumeSpec("/a", "rw")}


class _Srv(BaseServer):
    """A server whose readiness answers the test scripts."""

    SERVER_KEY = "srv"
    PROTOCOL = "p"
    CONTAINER_PORT = 1234

    def __init__(self) -> None:
        # Answers for successive probes; ``ready_default`` once they run out.
        self.ready: list[bool] = []
        self.ready_default = True
        self.seen: list[ServerConnection] = []
        self.own_volumes: dict[str, VolumeSpec] = {}
        self.scratch_volumes: dict[str, VolumeSpec] = {}
        # Called on each probe, to change Docker's state mid-poll.
        self.on_probe = self._nothing

    def _nothing(self) -> None:
        """The default probe hook: change nothing."""

    def get_command(self) -> list[str]:
        return ["serve"]

    def is_ready(self, connection: ServerConnection) -> bool:
        self.seen.append(connection)
        self.on_probe()
        return self.ready.pop(0) if self.ready else self.ready_default

    def get_volumes(self) -> dict[str, VolumeSpec]:
        return self.own_volumes

    def get_scratch_volumes(self) -> dict[str, VolumeSpec]:
        return self.scratch_volumes

    def get_build_args(self) -> dict[str, str]:
        return {"FROM_SERVER": "1"}

    def get_env(self, secret: str) -> dict[str, str]:
        return {"SRV_PASSWORD": secret}


def _settings(**overrides) -> ServerSettings:
    """Settings for image ``img`` with nothing else configured."""
    values: dict = {"image": "img", "build": None, "port": None, "volumes": {}}
    values.update(overrides)
    return ServerSettings(**values)


class _Run:
    """One launcher with its fake server and recorded sleeps."""

    def __init__(self, server: _Srv | None = None, **settings) -> None:
        self.server = server or _Srv()
        self.sleeps: list[float] = []
        self.launcher = ServerLauncher(
            self.server, _settings(**settings), environ={}, sleep=self.sleeps.append
        )

    def launch(self, workdir: str | None = None, dry_run: bool = False) -> LaunchResult:
        return self.launcher.launch(
            workdir=None if workdir is None else Path(workdir), dry_run=dry_run
        )

    def error(self, workdir: str | None = None, dry_run: bool = False) -> str:
        """The message of the error a launch raises."""
        with pytest.raises(PaddockEnvironmentError) as exc:
            self.launch(workdir, dry_run)
        return str(exc.value)


def _flags(argv: list[str], flag: str) -> list[str]:
    """Every value given to ``flag`` in ``argv``."""
    return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]


def _running(docker, **kwargs) -> dict:
    """A running, owned container holding secret ``theirs``."""
    return docker.container_entry(env=[f"{SECRET_ENV}=theirs"], **kwargs)


def test_launch_creates_a_missing_server(docker):
    run = _Run()
    result = run.launch()
    assert result.created is True
    assert result.drifted is False
    assert result.run_argv is not None
    assert result.run_argv == docker.ran("docker", "run")[0]
    assert result.connection.network == NAME
    assert result.connection.container_url == f"http://{NAME}:1234"
    assert result.connection.host_url == "http://127.0.0.1:32768"
    assert _flags(result.run_argv, "--label")[0] == "paddock.managed=server:srv"
    assert result.run_argv[-2:] == ["img", "serve"]


def test_mounts_are_the_servers_then_configured_then_scratch(docker):
    server = _Srv()
    server.own_volumes = {"/own": VolumeSpec("/own", "ro")}
    server.scratch_volumes = {"state": VolumeSpec("/state", "rw")}
    result = _Run(server, volumes=RW_A).launch()
    assert result.run_argv is not None
    assert _flags(result.run_argv, "-v") == [
        "/own:/own:ro",
        "/a:/a:rw",
        "state:/state:rw",
    ]


def test_a_configured_port_is_published(docker):
    result = _Run(port=4096).launch()
    assert result.run_argv is not None
    assert _flags(result.run_argv, "-p") == ["127.0.0.1:4096:1234"]


def test_secret_is_minted_and_exported(docker):
    result = _Run().launch()
    env = docker.env_of("docker", "run")
    secret = result.connection.secret
    assert len(secret) >= 32
    assert env[SECRET_ENV] == secret
    assert env["SRV_PASSWORD"] == secret


def test_each_server_gets_its_own_secret(docker):
    first = _Run().launch().connection.secret
    docker.container = None
    assert _Run().launch().connection.secret != first


def test_secret_never_appears_in_argv_logs_or_repr(docker, caplog):
    with caplog.at_level(logging.DEBUG):
        result = _Run().launch()
    secret = result.connection.secret
    assert result.run_argv is not None
    assert not any(secret in arg for arg in result.run_argv)
    assert not any(secret in record.getMessage() for record in caplog.records)
    assert secret not in repr(result)


def test_readiness_probe_gets_the_connection(docker):
    run = _Run()
    result = run.launch()
    assert run.server.seen == [result.connection]


def test_running_server_is_reused(docker):
    first = _Run().launch()
    run = _Run()
    result = run.launch()
    assert len(docker.ran("docker", "run")) == 1
    assert result.created is False
    assert result.run_argv is None
    assert result.drifted is False
    assert result.connection.secret == first.connection.secret
    assert len(run.server.seen) == 1


def test_running_server_without_a_secret_is_an_error(docker):
    docker.container = docker.container_entry()
    assert _Run().error() == (
        '[agent.server] Server "srv" is running without a secret paddock can '
        f"read; to recreate it: docker rm -f {NAME}"
    )


def test_drift_is_reported_not_acted_on(docker):
    _Run().launch()
    result = _Run(port=4096).launch()
    assert result.drifted is True
    assert docker.ran("docker", "rm") == []
    assert len(docker.ran("docker", "run")) == 1


def test_stopped_server_is_removed_by_id_and_recreated(docker):
    docker.container = docker.container_entry(status="exited", container_id="dead1")
    result = _Run().launch()
    assert result.created is True
    rm = docker.calls.index(["docker", "rm", "dead1"])
    assert rm < docker.calls.index(result.run_argv)


def test_created_leftover_with_an_error_is_removed_and_recreated(docker):
    docker.container = docker.container_entry(
        status="created", error="exec: not found", container_id="left1"
    )
    result = _Run().launch()
    assert result.created is True
    assert docker.ran("docker", "rm") == [["docker", "rm", "left1"]]


def test_a_starting_container_is_waited_for_not_removed(docker):
    starting = docker.container_entry(status="created")
    docker.inspect_script = [starting, starting, _running(docker)]
    run = _Run()
    result = run.launch()
    assert result.created is False
    assert result.connection.secret == "theirs"
    assert docker.ran("docker", "rm") == []
    assert docker.ran("docker", "run") == []
    assert run.sleeps == [0.5]


def test_a_container_stuck_starting_is_removed(docker):
    docker.container = docker.container_entry(status="created", container_id="stuck1")
    run = _Run()
    assert run.error() == (
        '[agent.server] Server "srv" was created but never started; it has '
        "been removed, so run again"
    )
    assert len(run.sleeps) == 60
    assert run.server.seen == []
    assert docker.ran("docker", "rm") == [["docker", "rm", "stuck1"]]


def test_foreign_container_is_refused(docker):
    docker.container = docker.container_entry(owner=None)
    assert _Run().error() == (
        f'[agent.server] A container named "{NAME}" exists that paddock did '
        "not create; remove or rename it"
    )
    assert docker.ran("docker", "rm") == []
    assert docker.ran("docker", "run") == []


def _lose_the_name(docker, winner: dict) -> None:
    """Make ``docker run`` fail as it does when ``winner`` took the name."""
    docker.run_returncode = 125
    docker.run_stderr = (
        "docker: Error response from daemon: Conflict. The container name "
        f'"/{NAME}" is already in use by container "abc".\n'
    )
    docker.container_after_failed_run = winner


def test_name_lost_to_a_foreign_container_is_refused(docker):
    _lose_the_name(docker, docker.container_entry(owner=None))
    assert "exists that paddock did not create" in _Run().error()


def test_name_conflict_is_another_paddocks_server(docker):
    _lose_the_name(docker, _running(docker))
    result = _Run().launch()
    assert result.connection.secret == "theirs"
    assert result.created is False
    assert result.run_argv is None


def test_readiness_is_polled(docker):
    run = _Run()
    run.server.ready = [False, False, True]
    run.launch()
    assert run.sleeps == [0.5, 0.5]


def test_readiness_times_out(docker):
    run = _Run()
    run.server.ready_default = False
    assert run.error() == (
        '[agent.server] Server "srv" was not ready after 30 seconds; see: '
        f"docker logs {NAME}"
    )
    assert len(run.server.seen) == 60
    assert len(run.sleeps) == 60
    assert docker.ran("docker", "rm") == []


def _stop(docker) -> None:
    """Mark the fake's container as exited."""
    docker.container["State"] = {"Error": "", "Running": False, "Status": "exited"}


def test_exit_during_start_is_reported(docker):
    run = _Run()
    run.server.ready_default = False

    def stop() -> None:
        _stop(docker)

    run.server.on_probe = stop
    assert run.error() == (
        f'[agent.server] Server "srv" stopped while starting; see: docker logs {NAME}'
    )
    assert len(run.server.seen) == 1
    assert docker.ran("docker", "rm") == []


def test_unpublished_port_is_polled_again(docker):
    docker.port_script = [None]
    run = _Run()
    run.launch()
    assert run.sleeps == [0.5]


def test_a_container_that_vanishes_while_polling_is_reported(docker):
    run = _Run()
    run.server.ready_default = False

    def vanish() -> None:
        docker.container = None

    run.server.on_probe = vanish
    assert "stopped while starting" in run.error()


def test_stopped_before_the_port_is_read_is_reported(docker):
    docker.inspect_script = [
        None,
        _running(docker),
        docker.container_entry(status="exited"),
    ]
    docker.port_script = [None]
    run = _Run()
    assert "stopped while starting" in run.error()
    assert run.server.seen == []


def _image_source(mocker):
    """Patch the image source factory; return ``(from_config, source)``."""
    source = mocker.Mock()
    from_config = mocker.patch(
        "paddock.docker.server.ImageSourceFactory.from_config", return_value=source
    )
    return from_config, source


BUILD: dict = {"args": {}, "context": None, "dockerfile": None, "policy": "daily"}


def test_image_is_prepared_only_on_create(docker, mocker):
    _, source = _image_source(mocker)
    _Run(build=BUILD).launch()
    source.refresh.assert_called_once_with("img")
    _Run(build=BUILD).launch()
    source.refresh.assert_called_once_with("img")


def test_image_is_not_prepared_without_build_settings(docker, mocker):
    from_config, _ = _image_source(mocker)
    _Run().launch()
    from_config.assert_not_called()


def test_image_failure_is_reported(docker, mocker):
    _, source = _image_source(mocker)
    source.refresh.side_effect = subprocess.CalledProcessError(3, ["docker", "pull"])
    assert _Run(build=BUILD).error() == (
        '[agent.server] Could not build or pull the image for server "srv": '
        "docker exited 3"
    )
    assert docker.ran("docker", "run") == []


def test_build_args_come_from_the_server(docker, mocker):
    from_config, _ = _image_source(mocker)
    _Run(build=BUILD).launch()
    from_config.assert_called_once_with(
        BUILD, agent_build_args={"FROM_SERVER": "1"}, environ={}
    )


def test_workdir_under_a_rw_identity_mount_passes(docker):
    assert _Run(volumes=RW_A).launch("/a/b/c").created is True


def test_workdir_equal_to_a_mount_point_passes(docker):
    assert _Run(volumes=RW_A).launch("/a").created is True


def _uncovered(mounts: str, recreate: bool = False) -> str:
    """The error for workdir ``/w`` not covered by ``mounts``."""
    text = (
        '[agent.server] Server "srv" does not have /w mounted read-write at '
        f"the same path; its mounts: {mounts}. Add a mount under "
        "[agents.srv.server.volumes] in your user config"
    )
    if recreate:
        text += f", then recreate the server: docker rm -f {NAME}"
    return text


def test_workdir_outside_every_mount_is_refused(docker):
    volumes = {"/b": VolumeSpec("/b", "rw"), "/a": VolumeSpec("/a", "ro")}
    assert _Run(volumes=volumes).error("/w") == _uncovered("/a:/a:ro, /b:/b:rw")


def test_workdir_refused_with_no_mounts_says_none(docker):
    assert _Run().error("/w") == _uncovered("none")


def test_workdir_refused_by_a_running_server_says_how_to_recreate(docker):
    _Run(volumes=RW_A).launch()
    assert _Run(volumes=RW_A).error("/w") == _uncovered("/a:/a:rw", recreate=True)


def test_workdir_under_a_readonly_mount_is_refused(docker):
    run = _Run(volumes={"/a": VolumeSpec("/a", "ro")})
    assert "does not have /a/b mounted" in run.error("/a/b")


def test_workdir_under_a_mount_of_another_host_path_is_refused(docker):
    run = _Run(volumes={"/other": VolumeSpec("/a", "rw")})
    assert "does not have /a/b mounted" in run.error("/a/b")


def test_workdir_shadowed_by_a_more_specific_mount_is_refused(docker):
    volumes = {"/a": VolumeSpec("/a", "rw"), "/other": VolumeSpec("/a/b", "rw")}
    assert "does not have /a/b/c mounted" in _Run(volumes=volumes).error("/a/b/c")


def test_workdir_shadowed_by_a_named_volume_is_refused(docker):
    server = _Srv()
    server.scratch_volumes = {"state": VolumeSpec("/a/b", "rw")}
    assert "does not have /a/b/c mounted" in _Run(server, volumes=RW_A).error("/a/b/c")


def test_sibling_prefix_does_not_cover(docker):
    assert "does not have /ab/c mounted" in _Run(volumes=RW_A).error("/ab/c")


def test_trailing_slash_on_a_container_path_still_matches(docker):
    run = _Run(volumes={"/a": VolumeSpec("/a/", "rw")})
    assert run.launch("/a/b").created is True


def test_the_servers_own_volume_can_cover_the_workdir(docker):
    server = _Srv()
    server.own_volumes = RW_A
    assert _Run(server).launch("/a/b").created is True


def test_the_servers_own_volume_can_shadow_the_workdir(docker):
    server = _Srv()
    server.own_volumes = {"/other": VolumeSpec("/a/b", "rw")}
    assert "does not have /a/b/c mounted" in _Run(server, volumes=RW_A).error("/a/b/c")


def test_running_server_is_judged_by_its_label_not_config(docker):
    _Run().launch()
    assert _Run(volumes={"/w": VolumeSpec("/w", "rw")}).error("/w") == _uncovered(
        "none", recreate=True
    )


def test_no_workdir_skips_the_check(docker):
    assert _Run().launch().created is True


def test_workdir_is_checked_before_anything_is_created(docker, mocker):
    _, source = _image_source(mocker)
    _Run(build=BUILD).error("/w")
    assert docker.ran("docker", "run") == []
    assert docker.ran("docker", "network", "create") == []
    source.refresh.assert_not_called()


def test_dry_run_creates_nothing(docker, mocker):
    _, source = _image_source(mocker)
    run = _Run(build=BUILD)
    result = run.launch(dry_run=True)
    assert docker.calls == [
        ["docker", "container", "inspect", NAME],
        ["docker", "network", "inspect", NAME],
    ]
    assert result.run_argv is not None
    assert result.run_argv[:3] == ["docker", "run", "-d"]
    assert result.connection.host_url == "http://127.0.0.1:<port>"
    assert result.connection.secret == "<secret>"
    assert result.created is False
    assert result.drifted is False
    assert run.sleeps == []
    assert run.server.seen == []
    source.refresh.assert_not_called()


def test_dry_run_refuses_a_foreign_network(docker):
    docker.network = docker.network_entry(owner=None)
    assert "A network named" in _Run().error(dry_run=True)


def test_dry_run_checks_the_workdir(docker):
    assert _Run().error("/w", dry_run=True) == _uncovered("none")


def test_dry_run_with_a_configured_port_shows_it(docker):
    result = _Run(port=4096).launch(dry_run=True)
    assert result.connection.host_url == "http://127.0.0.1:4096"


def test_dry_run_against_a_running_server_reads_it(docker):
    real = _Run().launch()
    run = _Run()
    result = run.launch(dry_run=True)
    assert result.connection == real.connection
    assert result.run_argv is None
    assert run.server.seen == []
    assert run.sleeps == []


def test_dry_run_against_a_running_server_reports_drift(docker):
    _Run().launch()
    assert _Run(port=4096).launch(dry_run=True).drifted is True


def test_dry_run_against_a_stopped_server_removes_nothing(docker):
    docker.container = docker.container_entry(
        status="exited", labels={"paddock.spec-hash": "stale"}
    )
    result = _Run().launch(dry_run=True)
    assert result.run_argv is not None
    assert result.drifted is False
    assert docker.ran("docker", "rm") == []


def test_dry_run_against_a_starting_server_uses_placeholders(docker):
    docker.container = docker.container_entry(status="created")
    result = _Run().launch(dry_run=True)
    assert result.run_argv is None
    assert result.connection.secret == "<secret>"


def test_dry_run_mints_no_secret(docker, mocker):
    mint = mocker.patch("paddock.docker.server.secrets.token_urlsafe")
    _Run().launch(dry_run=True)
    mint.assert_not_called()
