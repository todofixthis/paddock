from abc import ABC, abstractmethod
from typing import ClassVar

from class_registry.entry_points import EntryPointClassRegistry

from paddock.config.filters import VolumeSpec

agent_registry: EntryPointClassRegistry = EntryPointClassRegistry("paddock.agents")


class BaseAgent(ABC):
    AGENT_KEY: ClassVar[str]

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
