from paddock.config.agent_choice import UNNAMED_SERVER, AgentChoice


def test_whole_resets_the_server():
    """A whole value names the client and resets the server to unnamed."""
    assert AgentChoice.from_parts("claude") == {
        "client": "claude",
        "server": UNNAMED_SERVER,
    }


def test_false_is_the_shell_and_resets_the_server():
    """``False`` is the shell client, and resets the server like a string."""
    assert AgentChoice.from_parts(False) == {
        "client": False,
        "server": UNNAMED_SERVER,
    }


def test_halves_apply_after_the_whole():
    """Within one source the whole value applies first, then the halves."""
    assert AgentChoice.from_parts("claude", server="srv") == {
        "client": "claude",
        "server": "srv",
    }
    assert AgentChoice.from_parts("claude", client="other") == {
        "client": "other",
        "server": UNNAMED_SERVER,
    }


def test_a_half_alone_names_only_itself():
    """A half with no whole value leaves the other half unnamed."""
    assert AgentChoice.from_parts(None, server="srv") == {"server": "srv"}
    assert AgentChoice.from_parts(None, server=False) == {"server": False}


def test_nothing_given_is_none():
    """With nothing to choose there is no value at all."""
    assert AgentChoice.from_parts(None) is None
