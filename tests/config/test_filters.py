import filters as f

from paddock.config.filters import Agent, Volume


def test_volume_bare_path():
    """A bare container path (no mode) is valid and returned as-is."""
    assert f.FilterRunner(Volume, "/container/path").cleaned_data == "/container/path"


def test_volume_explicit_ro():
    """':ro' mode is valid and returned as-is."""
    assert (
        f.FilterRunner(Volume, "/container/path:ro").cleaned_data
        == "/container/path:ro"
    )


def test_volume_explicit_rw():
    """':rw' mode is valid and returned as-is."""
    assert (
        f.FilterRunner(Volume, "/container/path:rw").cleaned_data
        == "/container/path:rw"
    )


def test_volume_implicit_ro():
    """A path with no mode suffix has ':ro' appended."""
    # Implicit read-only: no mode suffix means the filter appends ':ro'
    assert f.FilterRunner(Volume, "/container/path").cleaned_data == "/container/path"


def test_volume_invalid():
    """A value with more than one colon-separated segment is invalid."""
    assert not f.FilterRunner(Volume, "not:a:valid:path").is_valid()


def test_agent_string():
    """A non-empty string agent name is valid."""
    assert f.FilterRunner(Agent, "claude").cleaned_data == "claude"


def test_agent_false_string():
    """The string 'false' is mapped to boolean False."""
    assert f.FilterRunner(Agent, "false").cleaned_data is False


def test_agent_true_rejected():
    """Boolean True is not a valid agent value."""
    assert not f.FilterRunner(Agent, True).is_valid()


def test_agent_false_bool():
    """Boolean False (already a bool) passes through."""
    assert f.FilterRunner(Agent, False).cleaned_data is False
