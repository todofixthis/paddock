from paddock.agents.servers import Secret
from paddock.docker.environment import ContainerEnvironment


def test_safe_values_are_flagged_verbatim_and_sorted():
    env = ContainerEnvironment({"B_URL": "http://srv:1", "A_MODE": "x y"})
    assert env.flags() == ["-e", "A_MODE=x y", "-e", "B_URL=http://srv:1"]
    assert env.secrets == {}
    assert env.safe == {"A_MODE": "x y", "B_URL": "http://srv:1"}


def test_a_marked_secret_is_flagged_by_name_only():
    env = ContainerEnvironment({"TOKEN": Secret("s3cr3t"), "URL": "u"})
    assert env.flags() == ["-e", "TOKEN", "-e", "URL=u"]
    assert env.secrets == {"TOKEN": "s3cr3t"}
    assert env.safe == {"URL": "u"}


def test_an_unmarked_value_holding_the_secret_is_secret():
    env = ContainerEnvironment(
        {"AUTH": "user:s3cr3t", "PLAIN": "s3cr3t", "URL": "u"}, secret="s3cr3t"
    )
    assert env.flags() == ["-e", "AUTH", "-e", "PLAIN", "-e", "URL=u"]
    assert env.secrets == {"AUTH": "user:s3cr3t", "PLAIN": "s3cr3t"}


def test_an_empty_secret_marks_nothing():
    assert ContainerEnvironment({"URL": "u"}, secret="").flags() == ["-e", "URL=u"]


def test_names_cover_both_kinds():
    env = ContainerEnvironment({"B": Secret("x"), "A": "y"})
    assert env.names == ["A", "B"]


def test_no_secret_value_reaches_a_repr():
    env = ContainerEnvironment({"TOKEN": Secret("s3cr3t"), "URL": "u"})
    assert "s3cr3t" not in repr(env)
    assert "s3cr3t" not in repr(Secret("s3cr3t"))
    assert "URL" in repr(env)


def test_equal_by_content():
    assert ContainerEnvironment({"A": Secret("x")}) == ContainerEnvironment(
        {"A": "x"}, secret="x"
    )
    assert ContainerEnvironment({"A": "x"}) != ContainerEnvironment({"A": "y"})
