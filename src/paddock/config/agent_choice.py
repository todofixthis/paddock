# The stored value of a server half that a whole ``agent`` value reset: "take
# the merged client's default". An ordinary string, so it survives ``DropEmpty``
# and a second pass through the schema (ADR 018).
UNNAMED_SERVER = "<default>"


class AgentChoice:
    """Builds the two-halves form of an ``agent`` value (ADR 018)."""

    @staticmethod
    def from_parts(
        whole: str | bool | None,
        *,
        client: str | bool | None = None,
        server: str | bool | None = None,
    ) -> dict[str, str | bool] | None:
        """Combine a whole ``agent`` value with either half, unvalidated.

        Within one source the whole value applies first: it names the client
        and resets the server to unnamed. The halves then override it.

        Args:
            whole: A client name, or ``False`` for the shell; ``None`` if the
                source gave no whole value.
            client: The client half alone, or ``None``.
            server: The server half alone, ``False`` meaning no server, or
                ``None``.

        Returns:
            A table holding the halves that were named, or ``None`` when
            nothing was given.
        """
        halves: dict[str, str | bool] = {}
        if whole is not None:
            halves = {"client": whole, "server": UNNAMED_SERVER}
        if client is not None:
            halves["client"] = client
        if server is not None:
            halves["server"] = server
        return halves or None
