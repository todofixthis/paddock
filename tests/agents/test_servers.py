import dataclasses

import pytest

from paddock.agents.servers import BaseServer, ServerConnection, server_registry


class MinimalServer(BaseServer):
    """The least a server must define."""

    SERVER_KEY = "minimal"
    PROTOCOL = "minimal"
    CONTAINER_PORT = 1234

    def get_command(self) -> list[str]:
        return ["serve"]

    def is_ready(self, connection: ServerConnection) -> bool:
        return True


def test_server_registry_is_empty_without_plugins() -> None:
    """No server is bundled yet.

    This changes when the first bundled server is registered.
    """
    assert list(server_registry) == []


def test_base_server_defaults() -> None:
    """A server that overrides nothing mounts, builds and exports nothing."""
    server = MinimalServer()
    assert server.get_volumes() == {}
    assert server.get_scratch_volumes() == {}
    assert server.get_build_args() == {}
    assert server.get_env("s") == {}
    assert server.DEFAULT_IMAGE is None
    assert server.REQUIRES_WORKDIR_MOUNT is False


def test_base_server_is_abstract() -> None:
    """BaseServer cannot be instantiated without its abstract methods."""
    with pytest.raises(TypeError):
        BaseServer()  # type: ignore[abstract]


def test_server_connection_is_immutable() -> None:
    """A connection cannot be altered once handed to a client."""
    connection = ServerConnection(
        container_url="http://c:1", host_url="http://h:2", network="n", secret="s"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        connection.secret = "other"  # type: ignore[misc]
