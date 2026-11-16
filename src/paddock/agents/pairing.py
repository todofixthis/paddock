from dataclasses import dataclass

from class_registry.base import BaseRegistry

from paddock.agents import BaseAgent, agent_registry
from paddock.agents.errors import AgentError
from paddock.agents.servers import BaseServer, server_registry


@dataclass(frozen=True)
class AgentPairing:
    """The client chosen for a run, and the server chosen beside it (ADR 018)."""

    client: BaseAgent
    """The client that runs in the per-run container."""

    server: BaseServer | None
    """The server chosen beside the client, or ``None`` for none."""

    @property
    def is_paired(self) -> bool:
        """Whether the client connects to the server.

        A client is paired with a server when both name the same protocol. A
        client with no protocol may be chosen beside a server without being
        connected to it.
        """
        return (
            self.server is not None
            and self.client.PROTOCOL is not None
            and self.client.PROTOCOL == self.server.PROTOCOL
        )

    @classmethod
    def resolve(
        cls,
        client_key: str,
        server_key: str | None,
        *,
        agents: BaseRegistry = agent_registry,
        servers: BaseRegistry = server_registry,
    ) -> "AgentPairing":
        """Look up the chosen client and server and check they can run together.

        Args:
            client_key: The chosen client's registry key.
            server_key: The chosen server's registry key, or ``None`` for none.
            agents: The registry of clients.
            servers: The registry of servers.

        Returns:
            The pairing, with both halves instantiated.

        Raises:
            AgentError: If either is not installed, or the client speaks a
                protocol the server does not.
        """
        if client_key not in agents:
            raise AgentError(
                f'[agent] Unknown agent "{client_key}"; '
                f"installed agents: {cls._installed(agents)}"
            )
        if server_key is not None and server_key not in servers:
            raise AgentError(
                f'[agent.server] Unknown server "{server_key}"; '
                f"installed servers: {cls._installed(servers)}"
            )

        client: BaseAgent = agents.get(client_key)
        server: BaseServer | None = None
        if server_key is not None:
            server = servers.get(server_key)

        if client.PROTOCOL is not None:
            needs = (
                f'[agent] Agent "{client_key}" needs a server that speaks '
                f'"{client.PROTOCOL}", but'
            )
            if server is None:
                raise AgentError(f"{needs} none is chosen; set agent.server")
            if server.PROTOCOL != client.PROTOCOL:
                raise AgentError(
                    f'{needs} server "{server_key}" speaks "{server.PROTOCOL}"'
                )
        return cls(client=client, server=server)

    @staticmethod
    def _installed(registry: BaseRegistry) -> str:
        """List a registry's keys for a message, or ``none`` when empty."""
        return ", ".join(sorted(str(key) for key in registry)) or "none"
