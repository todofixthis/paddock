import pytest
from class_registry import ClassRegistry

from paddock.agents import BaseAgent
from paddock.agents.errors import AgentError
from paddock.agents.pairing import AgentPairing
from paddock.agents.servers import BaseServer, ServerConnection


class _Client(BaseAgent):
    """A client that runs nothing."""

    def get_command(self) -> list[str]:
        return [self.AGENT_KEY]

    def get_volumes(self) -> dict:
        return {}


class _Paired(_Client):
    AGENT_KEY = "paired"
    PROTOCOL = "p"


class _Plain(_Client):
    AGENT_KEY = "plain"


class _Server(BaseServer):
    """A server that runs nothing."""

    CONTAINER_PORT = 1

    def get_command(self) -> list[str]:
        return [self.SERVER_KEY]

    def is_ready(self, connection: ServerConnection) -> bool:
        return True


class _Srv(_Server):
    SERVER_KEY = "srv"
    PROTOCOL = "p"


class _Other(_Server):
    SERVER_KEY = "other"
    PROTOCOL = "q"


def _agents() -> ClassRegistry:
    registry: ClassRegistry = ClassRegistry(attr_name="AGENT_KEY")
    registry.register(_Paired)
    registry.register(_Plain)
    return registry


def _servers(*classes: type[BaseServer]) -> ClassRegistry:
    registry: ClassRegistry = ClassRegistry(attr_name="SERVER_KEY")
    for cls in classes:
        registry.register(cls)
    return registry


def _resolve(client_key: str, server_key: str | None) -> AgentPairing:
    """Resolve a pairing against the fake registries."""
    return AgentPairing.resolve(
        client_key, server_key, agents=_agents(), servers=_servers(_Srv, _Other)
    )


def _error(client_key: str, server_key: str | None) -> str:
    """Return the message of the error a pairing raises."""
    with pytest.raises(AgentError) as exc:
        _resolve(client_key, server_key)
    return str(exc.value)


def test_matching_protocols_are_paired():
    """A client and a server naming the same protocol are paired."""
    pairing = _resolve("paired", "srv")
    assert pairing.is_paired is True
    assert isinstance(pairing.client, _Paired)
    assert isinstance(pairing.server, _Srv)


def test_plain_client_alone():
    """A client with no protocol needs no server."""
    pairing = _resolve("plain", None)
    assert pairing.server is None
    assert pairing.is_paired is False


def test_plain_client_beside_a_server_is_not_paired():
    """A client with no protocol may be chosen beside a server, unconnected."""
    pairing = _resolve("plain", "srv")
    assert isinstance(pairing.server, _Srv)
    assert pairing.is_paired is False


def test_unknown_client():
    assert _error("nope", None) == (
        '[agent] Unknown agent "nope"; installed agents: paired, plain'
    )


def test_unknown_client_is_reported_before_an_unknown_server():
    assert _error("nope", "nope").startswith("[agent] Unknown agent")


def test_unknown_server():
    assert _error("plain", "nope") == (
        '[agent.server] Unknown server "nope"; installed servers: other, srv'
    )


def test_unknown_server_lists_none_when_empty():
    with pytest.raises(AgentError) as exc:
        AgentPairing.resolve("plain", "nope", agents=_agents(), servers=_servers())
    assert str(exc.value) == (
        '[agent.server] Unknown server "nope"; installed servers: none'
    )


def test_protocol_client_needs_a_server():
    assert _error("paired", None) == (
        '[agent] Agent "paired" needs a server that speaks "p", but none is '
        "chosen; set agent.server"
    )


def test_protocol_client_needs_a_matching_server():
    assert _error("paired", "other") == (
        '[agent] Agent "paired" needs a server that speaks "p", but server '
        '"other" speaks "q"'
    )


def test_mismatched_protocols_are_not_paired():
    """is_paired compares the protocols, whatever resolve would allow."""
    assert AgentPairing(client=_Paired(), server=_Other()).is_paired is False


def test_protocol_client_without_a_server_is_not_paired():
    """is_paired needs a server, whatever resolve would allow."""
    assert AgentPairing(client=_Paired(), server=None).is_paired is False
