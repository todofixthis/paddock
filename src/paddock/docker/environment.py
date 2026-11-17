from collections.abc import Mapping

from paddock.agents.servers import Secret


class ContainerEnvironment:
    """A container's environment variables, each either safe or secret.

    A safe value is part of the ``docker run`` command, where the user can
    read it. A secret one is passed by name and travels in the subprocess
    environment, so it reaches no printed command and no process listing.
    """

    def __init__(
        self, variables: Mapping[str, str | Secret], *, secret: str | None = None
    ) -> None:
        """Sort the variables into safe and secret.

        Args:
            variables: Each variable's value, wrapped in :class:`Secret`
                where it must not be printed.
            secret: A secret no value may reveal: a plain value containing it
                is treated as secret too, so forgetting the wrapper cannot
                print it.
        """
        self.safe: dict[str, str] = {}
        self.secrets: dict[str, str] = {}
        for name, value in variables.items():
            if isinstance(value, Secret):
                self.secrets[name] = value.value
            elif secret and secret in value:
                self.secrets[name] = value
            else:
                self.safe[name] = value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ContainerEnvironment):
            return NotImplemented
        return (self.safe, self.secrets) == (other.safe, other.secrets)

    def __repr__(self) -> str:
        return (
            f"ContainerEnvironment(safe={self.safe!r}, "
            f"secrets={sorted(self.secrets)!r})"
        )

    @property
    def names(self) -> list[str]:
        """Every variable's name, sorted."""
        return sorted({*self.safe, *self.secrets})

    def flags(self) -> list[str]:
        """The ``-e`` flags for ``docker run``, sorted by name.

        A safe variable is ``-e NAME=value``; a secret one is ``-e NAME``,
        which Docker fills from the environment it is run with.
        """
        flags = []
        for name in self.names:
            flags += ["-e", f"{name}={self.safe[name]}" if name in self.safe else name]
        return flags
