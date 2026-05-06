from abc import ABC, abstractmethod
from typing import ClassVar

from class_registry.entry_points import EntryPointClassRegistry

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
    def get_volumes(self) -> dict[str, str]:
        """
        Host-path-keyed volume mounts specific to this agent.

        Values are '/container/path' or '/container/path:mode'.
        Example: {'/home/user/.claude': '/root/.claude:rw'}
        """

    def get_scratch_volumes(self, image: str) -> dict[str, str]:
        """
        Named Docker volumes (not host paths) to create and mount.

        Keys are volume names, values are container paths. Override when the agent
        needs persistent storage that must not be shared with the host.
        Example: {'paddock_ubuntu_22_04_claude': '/scratch'}
        """
        return {}

    def get_build_args(self) -> dict[str, str]:
        """
        Docker build args to pass when building the paddock base image.

        Used when the built-in Dockerfile is referenced in the build config.
        Example: {'AGENT': 'claude'}
        """
        return {}
