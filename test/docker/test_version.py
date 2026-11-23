import json
import subprocess

import pytest
from pytest_mock import MockerFixture

from paddock.config.errors import PaddockEnvironmentError
from paddock.docker.version import DockerVersion


def _stub_version(
    mocker,
    *,
    client: str | None = "1.44",
    server: str | None = "1.44",
    returncode: int = 0,
    stderr: str = "",
    stdout: str | None = None,
):
    """Stub ``docker version``'s JSON output.

    Args:
        mocker: pytest-mock fixture.
        client: The client's API version.
        server: The daemon's API version, or ``None`` for no daemon answer.
        returncode: The command's exit status.
        stderr: The command's standard error.
        stdout: Replaces the JSON output outright.

    Returns:
        The ``subprocess.run`` mock.
    """
    if stdout is None:
        stdout = json.dumps(
            {
                "Client": {"ApiVersion": client},
                "Server": None if server is None else {"ApiVersion": server},
            }
        )

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    return mocker.patch("paddock.docker.version.subprocess.run", side_effect=fake_run)


def _error(mocker, **kwargs) -> str:
    """The message ``require_minimum`` raises for a stubbed version."""
    _stub_version(mocker, **kwargs)
    with pytest.raises(PaddockEnvironmentError) as exc:
        DockerVersion.require_minimum()
    return str(exc.value)


_TOO_OLD = (
    "[docker] Agent servers need Docker Engine 25.0 or newer (API 1.44); found API 1.43"
)


def test_current_docker_passes(mocker: MockerFixture) -> None:
    run = _stub_version(mocker)
    DockerVersion.require_minimum()
    assert run.call_args.args[0] == ["docker", "version", "--format", "{{json .}}"]


def test_newer_docker_passes(mocker: MockerFixture) -> None:
    """Versions compare as numbers: 1.100 is newer than 1.44, not older."""
    _stub_version(mocker, client="1.52", server="1.100")
    DockerVersion.require_minimum()


def test_old_daemon_is_refused(mocker: MockerFixture) -> None:
    assert _error(mocker, server="1.43") == _TOO_OLD


def test_old_client_is_refused(mocker: MockerFixture) -> None:
    assert _error(mocker, client="1.43", server="1.56") == _TOO_OLD


def test_unreachable_daemon_is_reported(mocker: MockerFixture) -> None:
    message = _error(
        mocker,
        server=None,
        returncode=1,
        stderr="\nCannot connect to the Docker daemon at unix:///x. Is it running?\n",
    )
    assert message == (
        "[docker] Could not read the Docker version: Cannot connect to the "
        "Docker daemon at unix:///x. Is it running?"
    )


def test_unreadable_version_is_reported(mocker: MockerFixture) -> None:
    assert _error(mocker, stdout="not json") == (
        "[docker] Could not read the Docker version: unexpected output"
    )


def test_a_version_that_is_not_a_number_is_reported(mocker: MockerFixture) -> None:
    assert _error(mocker, server="edge") == (
        "[docker] Could not read the Docker version: unexpected output"
    )
