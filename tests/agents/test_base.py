from paddock.agents.claude import ClaudeAgent
from paddock.agents.servers import ServerConnection
from paddock.agents.shell import ShellAgent


def test_agent_defaults_preserve_todays_behaviour() -> None:
    """A bundled agent names no server or protocol and ignores a connection."""
    connection = ServerConnection(
        container_url="http://paddock-server-x:1",
        host_url="http://127.0.0.1:2",
        network="paddock-server-x",
        secret="s",
    )
    for agent in (ClaudeAgent(), ShellAgent()):
        assert agent.DEFAULT_SERVER is None
        assert agent.PROTOCOL is None
        assert agent.get_server_args(connection) == []
        assert agent.get_server_env(connection) == {}
