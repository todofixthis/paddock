import base64
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from paddock.agents import agent_registry
from paddock.agents.opencode import OpenCodeAgent, OpenCodeServer
from paddock.agents.pairing import AgentPairing
from paddock.agents.servers import ServerConnection, server_registry
from paddock.cli import parse_args
from paddock.config.filters import VolumeSpec
from paddock.config.loader import ConfigLoader

SECRET = "s3cr3t-s3cr3t"


class _Info(BaseHTTPRequestHandler):
    """Answer ``GET /api/info`` as OpenCode does: 200 with the password."""

    status_when_authorised = 200
    redirect_to: str | None = None

    def do_GET(self) -> None:
        expected = "Basic " + base64.b64encode(f"opencode:{SECRET}".encode()).decode()
        if self.path == "/elsewhere":
            self.send_response(200)
        elif self.redirect_to is not None:
            self.send_response(302)
            self.send_header("Location", self.redirect_to)
        elif self.path != "/api/info":
            self.send_response(404)
        elif self.headers.get("Authorization") != expected:
            self.send_response(401)
        else:
            self.send_response(self.status_when_authorised)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        """Keep the test output clean."""


@pytest.fixture
def info_url() -> Iterator[str]:
    """A local HTTP server standing in for OpenCode's."""
    httpd = HTTPServer(("127.0.0.1", 0), _Info)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
    _Info.status_when_authorised = 200
    _Info.redirect_to = None


def _connection(host_url: str, secret: str = SECRET) -> ServerConnection:
    return ServerConnection(
        container_url="http://paddock-server-opencode:4096",
        host_url=host_url,
        network="paddock-server-opencode",
        secret=secret,
    )


def test_server_is_registered() -> None:
    assert isinstance(server_registry["opencode"], OpenCodeServer)


def test_server_identity() -> None:
    server = OpenCodeServer()
    assert server.SERVER_KEY == "opencode"
    assert server.PROTOCOL == "opencode"
    assert server.CONTAINER_PORT == 4096
    assert server.DEFAULT_IMAGE is None
    assert server.REQUIRES_WORKDIR_MOUNT is True


def test_server_command_listens_on_every_interface() -> None:
    assert OpenCodeServer().get_command() == [
        "opencode",
        "serve",
        "--hostname",
        "0.0.0.0",
        "--port",
        "4096",
    ]


def test_server_env_sets_the_password_and_stops_self_updates() -> None:
    assert OpenCodeServer().get_env(SECRET) == {
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_PASSWORD": SECRET,
    }


def test_server_state_lives_in_named_volumes() -> None:
    server = OpenCodeServer()
    assert server.get_scratch_volumes() == {
        "paddock-server-opencode-data": VolumeSpec("/root/.local/share/opencode", "rw"),
        "paddock-server-opencode-state": VolumeSpec(
            "/root/.local/state/opencode", "rw"
        ),
    }
    assert server.get_volumes() == {}


def test_server_build_arg() -> None:
    assert OpenCodeServer().get_build_args() == {"AGENT": "opencode"}


def test_ready_when_info_answers_200(info_url: str) -> None:
    assert OpenCodeServer().is_ready(_connection(info_url)) is True


def test_not_ready_while_starting(info_url: str) -> None:
    _Info.status_when_authorised = 503
    assert OpenCodeServer().is_ready(_connection(info_url)) is False


def test_not_ready_with_the_wrong_password(info_url: str) -> None:
    assert OpenCodeServer().is_ready(_connection(info_url, "wrong")) is False


def test_not_ready_when_nothing_listens() -> None:
    assert OpenCodeServer().is_ready(_connection("http://127.0.0.1:1")) is False


def test_a_redirect_is_not_ready_and_is_not_followed(info_url: str) -> None:
    """Following one would carry the password to wherever it points."""
    _Info.redirect_to = f"{info_url}/elsewhere"
    assert OpenCodeServer().is_ready(_connection(info_url)) is False


def test_a_malformed_redirect_is_not_ready(info_url: str) -> None:
    _Info.redirect_to = "http://[bad/x"
    assert OpenCodeServer().is_ready(_connection(info_url)) is False


def test_probe_ignores_the_hosts_proxy(
    info_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server is on loopback; a proxy would never reach it."""
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    assert OpenCodeServer().is_ready(_connection(info_url)) is True


def test_client_is_registered() -> None:
    assert isinstance(agent_registry["opencode"], OpenCodeAgent)


def test_client_identity() -> None:
    client = OpenCodeAgent()
    assert client.AGENT_KEY == "opencode"
    assert client.DEFAULT_SERVER == "opencode"
    assert client.PROTOCOL == OpenCodeServer.PROTOCOL


def test_client_command_and_build_arg() -> None:
    client = OpenCodeAgent()
    assert client.get_command() == ["opencode"]
    assert client.get_build_args() == {"AGENT": "opencode"}


def test_client_mounts_nothing_from_the_host() -> None:
    assert OpenCodeAgent().get_volumes() == {}


def test_client_keeps_interface_state_in_a_named_volume() -> None:
    assert OpenCodeAgent().get_scratch_volumes("any-image") == {
        "paddock-client-opencode-state": VolumeSpec("/root/.local/state/opencode", "rw")
    }


def test_client_points_at_the_server_by_flag() -> None:
    connection = _connection("http://127.0.0.1:4096")
    assert OpenCodeAgent().get_server_args(connection) == [
        "--server",
        "http://paddock-server-opencode:4096",
    ]


def test_client_takes_the_password_from_the_environment() -> None:
    connection = _connection("http://127.0.0.1:4096")
    client = OpenCodeAgent()
    assert client.get_server_env(connection) == {
        "OPENCODE_DISABLE_AUTOUPDATE": "1",
        "OPENCODE_PASSWORD": SECRET,
    }
    assert SECRET not in " ".join(client.get_server_args(connection))


def test_choosing_the_client_brings_its_server(tmp_path: Path) -> None:
    """``agent = "opencode"`` resolves to the client paired with the server."""
    config_dir = tmp_path / ".config" / "paddock"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        'agent = "opencode"\nimage = "i"\n[agents.opencode.server]\nimage = "i"\n'
    )
    parsed = parse_args([])
    resolved = ConfigLoader().resolve(parsed, workdir=tmp_path, environ={})
    assert resolved.agent_key == "opencode"
    assert resolved.server_key == "opencode"
    assert resolved.server_settings is not None
    pairing = AgentPairing.resolve(resolved.agent_key, resolved.server_key)
    assert pairing.is_paired
