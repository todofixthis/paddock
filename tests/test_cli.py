import pytest

from paddock.cli import parse_args


def test_no_args():
    """Invoking paddock with no arguments yields all-None paddock flags and an empty command."""
    result = parse_args([])
    assert result.image is None
    assert result.agent is None
    assert result.command == []
    assert result.volumes == {}
    assert not result.dry_run
    assert not result.quiet


def test_image_flag():
    """--image sets the container image; no positional means empty command."""
    result = parse_args(["--image=ubuntu:22.04"])
    assert result.image == "ubuntu:22.04"
    assert result.command == []


def test_agent_flag():
    """--agent sets the agent name."""
    result = parse_args(["--agent=claude"])
    assert result.agent == "claude"


def test_positional_becomes_command():
    """
    A bare positional argument and everything after it becomes the container command.
    'claude' is interpreted as a program name, not the paddock --agent flag.
    '--agent=plan' is a flag passed to the claude program, not to paddock.
    Users who want to pass both --agent and a positional command must use '--'
    to disambiguate (e.g. paddock --agent=opencode -- claude --agent=plan).
    """
    result = parse_args(["claude", "--agent=plan"])
    assert result.command == ["claude", "--agent=plan"]
    assert result.agent is None


def test_paddock_flags_before_positional():
    """Paddock flags before the positional are parsed; the positional starts the command."""
    result = parse_args(["--image=foo", "claude", "--agent=plan"])
    assert result.image == "foo"
    assert result.command == ["claude", "--agent=plan"]


def test_double_dash_splits():
    """'--' explicitly ends paddock arguments; everything after is the container command."""
    result = parse_args(["--image=foo", "--", "--resume"])
    assert result.image == "foo"
    assert result.command == ["--resume"]


def test_double_dash_multiple_occurrences():
    """
    Multiple '--' occurrences: only the first is treated as a paddock/command split.
    Subsequent '--' are passed through to the container command unchanged.
    """
    result = parse_args(["--agent=opencode", "--", "--continue", "--", "auth", "login"])
    assert result.agent == "opencode"
    assert result.command == ["--continue", "--", "auth", "login"]


def test_double_dash_after_positional():
    """
    '--' after a positional arg: the positional already ended paddock parsing,
    so '--' passes through to the container command.
    """
    result = parse_args(["--agent=opencode", "web", "--", "--port=4096"])
    assert result.agent == "opencode"
    assert result.command == ["web", "--", "--port=4096"]


def test_unknown_flag_is_error():
    """An unrecognised flag before any positional or '--' exits non-zero."""
    with pytest.raises(SystemExit):
        parse_args(["--not-a-paddock-flag"])


def test_volume_flag():
    """--volume=/host:/container:rw mounts a volume with read-write access."""
    result = parse_args(["--volume=/host:/container:rw"])
    assert result.volumes == {"/host": "/container:rw"}


def test_volume_flag_repeated():
    """Multiple --volume flags accumulate into a dict keyed by host path."""
    result = parse_args(["--volume=/a:/ca", "--volume=/b:/cb:ro"])
    assert result.volumes == {"/a": "/ca", "/b": "/cb:ro"}


def test_volume_flag_no_mode():
    """--volume without a mode suffix stores the container path as-is (no ':ro' appended here)."""
    # Note: ':ro' is appended by the Volume filter during config schema validation,
    # not by the CLI parser. The CLI uses a different format than config.toml:
    # CLI: /host:/container[:mode]   (colon-separated host and container spec)
    # TOML: host_path = "container_path[:mode]"  (two separate fields)
    # _parse_volume() is intentionally NOT using the Volume filter for this reason.
    result = parse_args(["--volume=/host:/container"])
    assert result.volumes == {"/host": "/container"}


def test_dry_run_flag():
    """--dry-run prints the docker command and exits without running it."""
    result = parse_args(["--dry-run"])
    assert result.dry_run


def test_quiet_flag():
    """--quiet suppresses all log output."""
    result = parse_args(["--quiet"])
    assert result.quiet


def test_workdir_flag():
    """--workdir overrides the directory used to locate project config and as the cwd mount."""
    result = parse_args(["--workdir=/tmp/myproject"])
    assert result.workdir == "/tmp/myproject"


def test_config_file_flag():
    """--config-file injects an extra config file into the hierarchy after project config."""
    result = parse_args(["--config-file=/tmp/extra.toml"])
    assert result.config_file == "/tmp/extra.toml"


def test_build_flags():
    """Build config can be overridden via CLI flags."""
    result = parse_args(
        ["--build-dockerfile=/Dockerfile", "--build-context=.", "--build-policy=always"]
    )
    assert result.build_dockerfile == "/Dockerfile"
    assert result.build_context == "."
    assert result.build_policy == "always"
