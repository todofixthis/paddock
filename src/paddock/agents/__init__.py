from abc import ABC, abstractmethod
from typing import ClassVar

from class_registry.entry_points import EntryPointClassRegistry

from paddock.agents.servers import ServerConnection
from paddock.config.filters import VolumeSpec

agent_registry: EntryPointClassRegistry = EntryPointClassRegistry("paddock.agents")


def installed_agent_keys() -> list[str]:
    """List the registry keys of the installed agents, sorted, for messages."""
    return sorted(str(key) for key in agent_registry)


class BaseAgent(ABC):
    """The client half of an agent: what runs in the per-run container (ADR 018)."""

    AGENT_KEY: ClassVar[str]

    # The server ``agent = "<key>"`` brings with it; ``None`` for no server.
    DEFAULT_SERVER: ClassVar[str | None] = None

    # The server protocol this client speaks; ``None`` for a client that
    # needs no server. A client is paired with a server naming the same one.
    PROTOCOL: ClassVar[str | None] = None

    @abstractmethod
    def get_command(self) -> list[str]:
        """
        Default command to run in the container.

        Example: ['claude'] for ClaudeAgent, ['/bin/bash'] for ShellAgent.
        """

    @abstractmethod
    def get_volumes(self) -> dict[str, VolumeSpec]:
        """
        Host-path-keyed volume mounts specific to this agent.

        Values are :class:`~paddock.config.filters.VolumeSpec` instances.
        Example: {'/home/user/.claude': VolumeSpec('/root/.claude', 'rw')}
        """

    def get_scratch_volumes(self, image: str) -> dict[str, VolumeSpec]:
        """
        Named Docker volumes (not host paths) to create and mount.

        Keys are volume names, values are :class:`~paddock.config.filters.VolumeSpec`
        instances. Override when the agent needs persistent storage that must not
        be shared with the host.
        Example: {'paddock_ubuntu_22_04_claude': VolumeSpec('/scratch', 'rw')}
        """
        return {}

    def get_build_args(self) -> dict[str, str]:
        """
        Docker build args to pass when building the paddock base image.

        Used when the built-in Dockerfile is referenced in the build config.
        Example: {'AGENT': 'claude'}
        """
        return {}

    def get_server_args(self, connection: ServerConnection) -> list[str]:
        """
        Arguments that point this client at its paired server.

        Placed after the command and before any configured ``extra_args``.

        Args:
            connection: The paired server's address and secret.
        """
        return []

    def get_server_env(self, connection: ServerConnection) -> dict[str, str]:
        """
        Environment variables that connect this client to its paired server.

        Args:
            connection: The paired server's address and secret.
        """
        return {}
