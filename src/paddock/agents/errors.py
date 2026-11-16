class AgentError(Exception):
    """Raised when the chosen client and server cannot be run together.

    Its message is the full line to show the user.
    """
