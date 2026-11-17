from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from class_registry.entry_points import EntryPointClassRegistry

from paddock.config.filters import VolumeSpec

server_registry: EntryPointClassRegistry = EntryPointClassRegistry("paddock.servers")


@dataclass(frozen=True)
class ServerConnection:
    """What a running server hands a client so it can connect."""

    container_url: str
    """The server's address from a container on its network."""

    host_url: str
    """The server's address from the host, on loopback."""

    network: str
    """The Docker network the server is on."""

    secret: str = field(repr=False)
    """The shared secret the server was started with; kept out of ``repr``."""


@dataclass(frozen=True)
class Secret:
    """An environment variable's value that paddock must never print.

    Return one from :meth:`BaseServer.get_env` or
    :meth:`~paddock.agents.BaseAgent.get_server_env` for a value derived from
    the secret, such as an encoded credential. A value containing the secret
    itself is treated as secret without it.

    Nothing detects a derived value left unwrapped: it is printed, and on a
    server every later run warns that its settings have drifted.
    """

    value: str = field(repr=False)
    """The value the container receives."""


class BaseServer(ABC):
    """The server half of an agent: one long-lived, shared container (ADR 018).

    A client is paired with a server when both name the same ``PROTOCOL``.
    Subclasses register under the ``paddock.servers`` entry-point group.
    """

    SERVER_KEY: ClassVar[str]
    PROTOCOL: ClassVar[str]
    CONTAINER_PORT: ClassVar[int]

    # The image to run when ``agents.<key>.server.image`` is unset; ``None``
    # makes that setting required.
    DEFAULT_IMAGE: ClassVar[str | None] = None

    # ``True`` for a server that runs the agent's tools in the project, which
    # must therefore have the workdir mounted at its own path.
    REQUIRES_WORKDIR_MOUNT: ClassVar[bool] = False

    @abstractmethod
    def get_command(self) -> list[str]:
        """
        Command that starts the server in its container.

        Example: ['opencode', 'serve', '--hostname', '0.0.0.0'].
        """

    @abstractmethod
    def is_ready(self, connection: ServerConnection) -> bool:
        """
        Report whether the server is accepting clients.

        Probed from the host through ``connection.host_url``.
        """

    def get_volumes(self) -> dict[str, VolumeSpec]:
        """
        Host-path-keyed volume mounts the server itself needs.

        Mounts the user configures are separate and need not be repeated.
        """
        return {}

    def get_scratch_volumes(self) -> dict[str, VolumeSpec]:
        """
        Named Docker volumes (not host paths) for the server's own state.

        Keys are volume names, values are
        :class:`~paddock.config.filters.VolumeSpec` instances.
        """
        return {}

    def get_build_args(self) -> dict[str, str]:
        """Docker build args to pass when paddock builds the server's image."""
        return {}

    def get_env(self, secret: str) -> Mapping[str, str | Secret]:
        """
        Environment variables to start the server with.

        Paddock prints each value in the server's ``docker run`` command,
        except one that contains ``secret`` or is wrapped in :class:`Secret`.
        Wrap any value derived from ``secret`` that no longer contains it.
        ``PADDOCK_SERVER_SECRET`` is paddock's own and overrides one set here.

        Args:
            secret: The shared secret paddock minted for this server.
        """
        return {}
