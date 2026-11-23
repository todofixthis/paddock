import logging
import shlex
import subprocess
from pathlib import Path

import pytest
from class_registry import ClassRegistry
from pytest_mock import MockerFixture

from paddock.__main__ import run
from paddock.agents import BaseAgent
from paddock.agents.servers import BaseServer, ServerConnection
from paddock.config.errors import PaddockEnvironmentError
from paddock.config.filters import VolumeSpec
from paddock.config.project_dir import ProjectDirManager
from paddock.docker.server import LaunchResult, ServerLauncher
from paddock.docker.version import DockerVersion


def _write_user_config(home: Path, contents: str) -> None:
    """Write the user config a test loads.

    ``isolate_environment`` (autouse) sets ``$HOME`` to ``tmp_path``, so the
    default user config path resolves under it.

    Args:
        home: The temp directory standing in for ``$HOME``.
        contents: TOML body to write.
    """
    config_dir = home / ".config" / "paddock"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(contents)


@pytest.fixture
def minimal_config(tmp_path: Path) -> Path:
    _write_user_config(tmp_path, 'image = "ubuntu:22.04"\nagent = "claude"\n')
    return tmp_path


def test_dry_run_exits_zero(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run prints the docker command and exits 0 without invoking docker."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run"])
    assert exc.value.code == 0
    mock_run.assert_not_called()
    captured = capsys.readouterr()
    assert "docker" in captured.out


def test_dry_run_prints_a_re_runnable_command(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The echoed docker command quotes argv elements containing spaces.

    A container command like ``bash -c 'cat /probe.txt'`` must be echoed
    with the single-quoted argument intact, so pasting the printed line
    back into a shell reproduces the same argv rather than splitting
    "cat /probe.txt" into two words.
    """
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run", "bash", "-c", "cat /probe.txt"])
    assert exc.value.code == 0
    mock_run.assert_not_called()
    captured = capsys.readouterr()
    assert "bash -c 'cat /probe.txt'" in captured.out
    assert captured.out.split()[0] == "docker"


@pytest.mark.parametrize(
    ("argv", "expected_tail"),
    [
        (["--", "fix this bug"], "ubuntu:22.04 claude 'fix this bug'"),
        (["--", "--resume"], "ubuntu:22.04 claude --resume"),
        (["--", "claude"], "ubuntu:22.04 claude claude"),
        (["--", "/bin/bash"], "ubuntu:22.04 claude /bin/bash"),
        (["/bin/bash"], "ubuntu:22.04 /bin/bash"),
        (["fix this bug"], "ubuntu:22.04 'fix this bug'"),
    ],
)
def test_container_command(
    argv: list[str],
    expected_tail: str,
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Args after '--' extend the agent's command; a positional replaces it."""
    monkeypatch.chdir(minimal_config)
    mocker.patch("paddock.__main__.subprocess.run")
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run", "--agent=claude", *argv])
    assert exc.value.code == 0
    assert capsys.readouterr().out.rstrip("\n").endswith(expected_tail)


def test_quiet_suppresses_all_output(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--quiet produces no output at all."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mock_run.return_value.returncode = 0
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--quiet"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_missing_image_exits_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Missing required 'image' config exits with code 1."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1


def test_runs_docker(
    minimal_config: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A valid config invokes 'docker run' with a docker argv."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mock_run.return_value.returncode = 0
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 0
    mock_run.assert_called_once()
    docker_argv = mock_run.call_args[0][0]
    assert docker_argv[0] == "docker"


def test_dry_run_skips_image_build(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--dry-run must not trigger an image build even when build config is present."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ubuntu:22.04\n")
    _write_user_config(
        tmp_path,
        'image = "myimage:latest"\nagent = "claude"\n\n'
        f'[build]\ndockerfile = "{dockerfile}"\n',
    )
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    mock_build = mocker.patch("paddock.docker.build.ImageBuilder.refresh")
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run"])
    assert exc.value.code == 0
    mock_build.assert_not_called()


def _write_pull_config(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configure a daily policy with no Dockerfile, so paddock pulls ``image``.

    Args:
        tmp_path: The temp directory standing in for ``$HOME`` and the workdir.
        mocker: pytest-mock fixture.
        monkeypatch: pytest's monkeypatch fixture.
    """
    _write_user_config(
        tmp_path,
        'image = "ghcr.io/example/agent:python"\nagent = "claude"\n\n'
        '[build]\npolicy = "daily"\n',
    )
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )


def test_policy_without_dockerfile_pulls_image(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build policy with no Dockerfile pulls the image instead of building."""
    _write_pull_config(tmp_path, mocker, monkeypatch)
    mock_pull = mocker.patch(
        "paddock.docker.pull.ImagePuller.refresh", return_value=True
    )
    mock_build = mocker.patch("paddock.docker.build.ImageBuilder.refresh")
    mock_run = mocker.patch(
        "paddock.__main__.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0),
    )
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 0
    mock_pull.assert_called_once_with("ghcr.io/example/agent:python")
    mock_build.assert_not_called()
    mock_run.assert_called_once()


def test_failed_pull_exits_without_running(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A due pull that fails stops paddock with Docker's exit status."""
    _write_pull_config(tmp_path, mocker, monkeypatch)
    mocker.patch(
        "paddock.docker.pull.ImagePuller.refresh",
        side_effect=subprocess.CalledProcessError(1, ["docker", "pull"]),
    )
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1
    mock_run.assert_not_called()


def test_dry_run_skips_image_pull(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run must not pull, just as it never builds."""
    _write_pull_config(tmp_path, mocker, monkeypatch)
    mock_pull = mocker.patch("paddock.docker.pull.ImagePuller.refresh")
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run"])
    assert exc.value.code == 0
    mock_pull.assert_not_called()


def test_policy_with_dockerfile_builds_image(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a Dockerfile set, the policy builds the image and never pulls."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ubuntu:22.04\n")
    _write_user_config(
        tmp_path,
        'image = "myimage:latest"\nagent = "claude"\n\n'
        f'[build]\ndockerfile = "{dockerfile}"\npolicy = "daily"\n',
    )
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    mock_build = mocker.patch(
        "paddock.docker.build.ImageBuilder.refresh", return_value=False
    )
    mock_pull = mocker.patch("paddock.docker.pull.ImagePuller.refresh")
    mocker.patch(
        "paddock.__main__.subprocess.run",
        return_value=subprocess.CompletedProcess([], 0),
    )
    with pytest.raises(SystemExit):
        run([])
    mock_build.assert_called_once()
    mock_pull.assert_not_called()


def test_paddock_dir_not_a_directory_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.paddock`` file (not a directory) exits 1 with a stderr message."""
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = "claude"\n'
        "[config.allowlist]\nproject_toml = true\n",
    )
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".paddock").write_text("oops")
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert ".paddock" in captured.err


def test_help_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """--help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        run(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_unknown_agent_exits_one(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unregistered agent key reports the installed agents and exits 1.

    The .paddock manager is never entered: checking that the directory is
    absent afterwards would pass either way, since the manager removes one it
    created.
    """
    entered = mocker.spy(ProjectDirManager, "__enter__")
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\n[config.allowlist]\nproject_toml = true\n',
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run(["--agent=bogus", "--dry-run"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        '[agent] Unknown agent "bogus"; installed agents: claude, false, opencode'
    )
    entered.assert_not_called()
    assert not (tmp_path / ".paddock").exists()


def test_relative_workdir_is_resolved(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative --workdir reaches docker as an absolute path."""
    _write_user_config(tmp_path, 'image = "ubuntu:22.04"\nagent = "claude"\n')
    project = tmp_path / "rel"
    project.mkdir()
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--workdir=rel", "--dry-run"])
    assert exc.value.code == 0
    resolved = str(project.resolve())
    out = capsys.readouterr().out
    assert f"--workdir={resolved}" in out
    assert f"-v {resolved}:{resolved}:rw" in out


def test_symlinked_workdir_is_resolved(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A symlinked --workdir mounts the real path.

    The resolved path is also what ``[projects]`` is keyed on.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = "claude"\n'
        f'[projects."{real.resolve()}"]\nimage = "override:1"\n',
    )
    monkeypatch.chdir(tmp_path)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run([f"--workdir={link}", "--dry-run"])
    assert exc.value.code == 0
    resolved = str(real.resolve())
    out = capsys.readouterr().out
    assert f"--workdir={resolved}" in out
    assert f"-v {resolved}:{resolved}:rw" in out
    assert str(link) not in out
    assert "override:1" in out


def test_missing_workdir_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A nonexistent --workdir exits 1 with a config-style message.

    No user config is written: ``_resolve_workdir`` exits before the loader
    reads one.
    """
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "nope"
    with pytest.raises(SystemExit) as exc:
        run([f"--workdir={missing}", "--dry-run"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        f'[workdir] Path "{missing}" does not exist or is not a directory'
    )


def test_workdir_that_is_a_file_exits_one(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A --workdir naming a file fails the same way as a missing one."""
    monkeypatch.chdir(tmp_path)
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("not a directory")
    with pytest.raises(SystemExit) as exc:
        run([f"--workdir={not_a_dir}", "--dry-run"])
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert captured.err.strip() == (
        f'[workdir] Path "{not_a_dir}" does not exist or is not a directory'
    )


def test_container_exit_status_is_propagated(
    minimal_config: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """paddock exits with the docker process's return code."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mock_run.return_value.returncode = 3
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 3


def test_logs_every_mounted_volume(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each ``-v`` in the docker command has a matching "Mounting" line.

    Agent volumes (``~/.claude``, ``~/.claude.json``) were once mounted but
    never logged, because the log read only the config's volumes.
    """
    (minimal_config / ".claude.json").write_text("{}")
    monkeypatch.chdir(minimal_config)
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with caplog.at_level("INFO", logger="paddock"), pytest.raises(SystemExit):
        run(["--dry-run"])
    argv = capsys.readouterr().out.split()
    mounted = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-v"]
    logged = [
        record.getMessage().removeprefix("Mounting ").replace(" -> ", ":", 1)
        for record in caplog.records
        if record.getMessage().startswith("Mounting ")
    ]
    assert f"{minimal_config / '.claude.json'}:/root/.claude.json:rw" in mounted
    assert logged == mounted


def test_container_exit_status_survives_failed_paddock_dir_removal(
    tmp_path: Path, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``.paddock`` that won't delete must not mask the container's status.

    Docker Desktop on macOS can briefly deny ``rmdir`` after the container
    exits. The error once escaped ``ProjectDirManager.__exit__`` and replaced
    the ``SystemExit``, so paddock exited 1 with a traceback.
    """
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = "claude"\n'
        "[config.allowlist]\nproject_toml = true\n",
    )
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / ".paddock").exists()
    mock_run = mocker.patch("paddock.__main__.subprocess.run")
    mock_run.return_value.returncode = 37
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    mocker.patch("paddock.config.project_dir.sleep")
    rmdir = mocker.patch.object(
        Path, "rmdir", autospec=True, side_effect=PermissionError(13, "denied")
    )
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 37
    rmdir.assert_called()


_EXTRA_ARGS_CONFIG = (
    'image = "ubuntu:22.04"\n'
    "agent = {agent}\n"
    '[agents.claude]\nextra_args = ["--resume"]\n'
    '[agents.false]\nextra_args = ["-l"]\n'
)


def _dry_run_argv(
    capsys: pytest.CaptureFixture[str], mocker: MockerFixture, argv: list[str]
) -> list[str]:
    """Run paddock with ``--dry-run`` and return the printed docker argv.

    Args:
        capsys: pytest's capture fixture.
        mocker: pytest-mock's fixture, to stub the container-name lookup.
        argv: Paddock arguments to follow ``--dry-run``.

    Returns:
        The printed ``docker run`` line, split as a shell would split it.
    """
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run", *argv])
    assert exc.value.code == 0
    return shlex.split(capsys.readouterr().out)


def test_dry_run_applies_extra_args_from_config(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """extra_args follow the agent's command and precede the tokens after --.

    An argument holding a space and shell metacharacters stays one token,
    and the printed line stays re-runnable.
    """
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = "claude"\n[agents.claude]\n'
        'extra_args = ["--append-system-prompt", "be brief; no $HOME"]\n',
    )
    monkeypatch.chdir(tmp_path)
    argv = _dry_run_argv(capsys, mocker, ["--", "fix it"])
    assert argv[-4:] == [
        "claude",
        "--append-system-prompt",
        "be brief; no $HOME",
        "fix it",
    ]


def test_replacement_command_ignores_extra_args(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement command drops extra_args with the agent's command."""
    _write_user_config(tmp_path, _EXTRA_ARGS_CONFIG.format(agent='"claude"'))
    monkeypatch.chdir(tmp_path)
    argv = _dry_run_argv(capsys, mocker, ["/bin/bash"])
    assert argv[-2:] == ["ubuntu:22.04", "/bin/bash"]
    assert "--resume" not in argv


def test_shell_agent_uses_its_own_extra_args(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``agent = false`` finds the settings keyed by the string "false"."""
    _write_user_config(tmp_path, _EXTRA_ARGS_CONFIG.format(agent="false"))
    monkeypatch.chdir(tmp_path)
    argv = _dry_run_argv(capsys, mocker, [])
    assert argv[-3:] == ["ubuntu:22.04", "/bin/bash", "-l"]


def test_cli_agent_switch_uses_that_agents_extra_args(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--agent switches which agent's extra_args apply."""
    _write_user_config(tmp_path, _EXTRA_ARGS_CONFIG.format(agent='"claude"'))
    monkeypatch.chdir(tmp_path)
    argv = _dry_run_argv(capsys, mocker, ["--agent=false"])
    assert argv[-3:] == ["ubuntu:22.04", "/bin/bash", "-l"]


def test_no_agents_table_leaves_the_command_alone(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without an agents table the agent's command is unchanged."""
    monkeypatch.chdir(minimal_config)
    argv = _dry_run_argv(capsys, mocker, [])
    assert argv[-2:] == ["ubuntu:22.04", "claude"]


def test_unknown_agent_settings_warn_and_run(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings for a name no agent has warn once and are ignored (ADR 017).

    The installed ``false`` draws no warning. ``at_level`` re-enables
    logging, which an earlier ``--quiet`` test disables process-wide.
    """
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = "claude"\n'
        '[agents.claud]\nextra_args = ["-x"]\n'
        '[agents.false]\nextra_args = ["-l"]\n',
    )
    monkeypatch.chdir(tmp_path)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        argv = _dry_run_argv(capsys, mocker, [])
    assert argv[-2:] == ["ubuntu:22.04", "claude"]
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert warnings == [
        '[agents.claud] No agent named "claud" is installed, so its settings '
        "are ignored; installed agents: claude, false, opencode"
    ]


def test_cli_client_override_runs_that_client(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--agent-client switches the client the container runs."""
    monkeypatch.chdir(minimal_config)
    argv = _dry_run_argv(capsys, mocker, ["--agent-client=false"])
    assert argv[-2:] == ["ubuntu:22.04", "/bin/bash"]


_UNKNOWN_SERVER = '[agent.server] Unknown server "nope"; installed servers: opencode'


def test_unknown_server_exits_one(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An uninstalled server stops the run before .paddock is created.

    The .paddock manager is never entered: checking that the directory is
    absent afterwards would pass either way, since the manager removes one it
    created.
    """
    entered = mocker.spy(ProjectDirManager, "__enter__")
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = { server = "nope" }\n'
        "[config.allowlist]\nproject_toml = true\n",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run"])
    assert exc.value.code == 1
    assert capsys.readouterr().err.strip() == _UNKNOWN_SERVER
    entered.assert_not_called()


def test_cli_server_override_is_checked(
    capsys: pytest.CaptureFixture[str],
    minimal_config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--agent-server names a server that must be installed."""
    monkeypatch.chdir(minimal_config)
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run", "--agent-server=nope"])
    assert exc.value.code == 1
    assert capsys.readouterr().err.strip() == _UNKNOWN_SERVER


def test_server_false_runs_without_one(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``server = false`` is a valid choice of no server."""
    _write_user_config(
        tmp_path,
        'image = "ubuntu:22.04"\nagent = { client = "claude", server = false }\n',
    )
    monkeypatch.chdir(tmp_path)
    argv = _dry_run_argv(capsys, mocker, [])
    assert argv[-2:] == ["ubuntu:22.04", "claude"]


class _Client(BaseAgent):
    """A client whose command is ``paired`` and which can address a server."""

    def get_command(self) -> list[str]:
        return ["paired"]

    def get_volumes(self) -> dict[str, VolumeSpec]:
        return {}

    def get_server_args(self, connection: ServerConnection) -> list[str]:
        return ["--server", connection.container_url]

    def get_server_env(self, connection: ServerConnection) -> dict[str, str]:
        return {"SRV_PASSWORD": connection.secret, "SRV_URL": connection.container_url}


class _Paired(_Client):
    """A client that speaks protocol ``p`` and defaults to server ``srv``."""

    AGENT_KEY = "paired"
    DEFAULT_SERVER = "srv"
    PROTOCOL = "p"


class _Plain(_Client):
    """A client that speaks no server protocol."""

    AGENT_KEY = "plain"


class _Srv(BaseServer):
    """A server that needs no workdir mount."""

    SERVER_KEY = "srv"
    PROTOCOL = "p"
    CONTAINER_PORT = 1234
    DEFAULT_IMAGE = "srv-img"

    def get_command(self) -> list[str]:
        return ["serve"]

    def is_ready(self, connection: ServerConnection) -> bool:
        return True


class _ToolSrv(_Srv):
    """A server that runs tools in the project."""

    REQUIRES_WORKDIR_MOUNT = True


_SECRET = "s3cr3t-never-shown"
_CONNECTION = ServerConnection(
    container_url="http://paddock-server-srv:1234",
    host_url="http://127.0.0.1:32768",
    network="paddock-server-srv",
    secret=_SECRET,
)
_SERVER_ARGV = ["docker", "run", "-d", "--name", "paddock-server-srv", "srv-img"]


class _ServerRun:
    """A run against fake registries, with Docker and the launcher stubbed."""

    def __init__(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        config: str = 'agent = "paired"\n',
        server: type[BaseServer] = _Srv,
        result: LaunchResult | None = None,
    ) -> None:
        _write_user_config(tmp_path, 'image = "img"\n' + config)
        monkeypatch.chdir(tmp_path)
        self.agents: ClassRegistry[BaseAgent] = ClassRegistry(attr_name="AGENT_KEY")
        self.agents.register(_Paired)
        self.agents.register(_Plain)
        self.servers: ClassRegistry[BaseServer] = ClassRegistry(attr_name="SERVER_KEY")
        self.servers.register(server)
        self.workdir = tmp_path.resolve()
        self.docker = mocker.patch("paddock.__main__.subprocess.run")
        self.docker.return_value.returncode = 0
        self.version = mocker.patch.object(DockerVersion, "require_minimum")
        self.launch = mocker.patch.object(
            ServerLauncher,
            "launch",
            return_value=result or LaunchResult(_CONNECTION, False, False, None),
        )
        mocker.patch(
            "paddock.docker.builder.DockerCommandBuilder._container_name_available",
            return_value=True,
        )

    def run(self, *argv: str) -> int:
        """Run paddock and return its exit status."""
        with pytest.raises(SystemExit) as exc:
            run(list(argv), agents=self.agents, servers=self.servers)
        assert isinstance(exc.value.code, int)
        return exc.value.code


def test_paired_run_starts_the_server_then_the_client(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paired = _ServerRun(mocker, tmp_path, monkeypatch)
    assert paired.run() == 0
    paired.launch.assert_called_once()
    argv = paired.docker.call_args.args[0]
    assert argv[argv.index("--network") + 1] == "paddock-server-srv"
    assert argv[-4:] == ["img", "paired", "--server", "http://paddock-server-srv:1234"]
    flags = [argv[i + 1] for i, a in enumerate(argv) if a == "-e"]
    assert flags == ["SRV_PASSWORD", "SRV_URL=http://paddock-server-srv:1234"]
    env = paired.docker.call_args.kwargs["env"]
    assert env["SRV_PASSWORD"] == _SECRET
    assert "SRV_URL" not in env
    assert env["HOME"] == str(tmp_path)


def test_server_line_is_printed_before_the_client_line(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = LaunchResult(_CONNECTION, True, False, _SERVER_ARGV)
    assert _ServerRun(mocker, tmp_path, monkeypatch, result=result).run() == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0] == shlex.join(_SERVER_ARGV)
    assert lines[1].startswith("docker run --rm -it ")


def test_a_reused_server_prints_only_the_client_line(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ServerRun(mocker, tmp_path, monkeypatch).run() == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("docker run --rm -it ")


def test_quiet_prints_no_server_line(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = LaunchResult(_CONNECTION, True, False, _SERVER_ARGV)
    assert _ServerRun(mocker, tmp_path, monkeypatch, result=result).run("--quiet") == 0
    assert capsys.readouterr().out == ""


def test_secret_is_never_printed_or_logged(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = LaunchResult(_CONNECTION, True, True, _SERVER_ARGV)
    with caplog.at_level(logging.DEBUG):
        assert _ServerRun(mocker, tmp_path, monkeypatch, result=result).run() == 0
    captured = capsys.readouterr()
    assert _SECRET not in captured.out
    assert _SECRET not in captured.err
    assert not any(_SECRET in record.getMessage() for record in caplog.records)


def test_drift_warns_with_the_recreate_command(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = LaunchResult(_CONNECTION, False, True, None)
    with caplog.at_level(logging.WARNING, logger="paddock"):
        assert _ServerRun(mocker, tmp_path, monkeypatch, result=result).run() == 0
    assert [r.getMessage() for r in caplog.records] == [
        'Server "srv" is running with settings that differ from your config; '
        "they apply when it is recreated: docker rm -f paddock-server-srv"
    ]


def test_no_drift_no_warning(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with caplog.at_level(logging.WARNING, logger="paddock"):
        assert _ServerRun(mocker, tmp_path, monkeypatch).run() == 0
    assert caplog.records == []


_UNPAIRED = 'agent = { client = "plain", server = "srv" }\n'


def test_unpaired_client_beside_a_server_is_not_connected(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unpaired = _ServerRun(
        mocker, tmp_path, monkeypatch, config=_UNPAIRED, server=_ToolSrv
    )
    with caplog.at_level(logging.INFO, logger="paddock"):
        assert unpaired.run() == 0
    assert unpaired.launch.call_args.kwargs == {"workdir": None, "dry_run": False}
    argv = unpaired.docker.call_args.args[0]
    assert "--network" not in argv
    assert "-e" not in argv
    assert argv[-2:] == ["img", "paired"]
    assert "SRV_PASSWORD" not in unpaired.docker.call_args.kwargs["env"]
    assert 'Server: srv (not connected: agent "plain" speaks no server protocol)' in [
        r.getMessage() for r in caplog.records
    ]


def test_paired_run_logs_the_server_address(
    caplog: pytest.LogCaptureFixture,
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with caplog.at_level(logging.INFO, logger="paddock"):
        assert _ServerRun(mocker, tmp_path, monkeypatch).run() == 0
    assert "Server: srv (http://127.0.0.1:32768)" in [
        r.getMessage() for r in caplog.records
    ]


def test_workdir_is_passed_when_the_server_needs_it(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paired = _ServerRun(mocker, tmp_path, monkeypatch, server=_ToolSrv)
    assert paired.run() == 0
    assert paired.launch.call_args.kwargs == {
        "workdir": paired.workdir,
        "dry_run": False,
    }


def test_workdir_is_not_passed_when_the_server_does_not_need_it(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paired = _ServerRun(mocker, tmp_path, monkeypatch)
    assert paired.run() == 0
    assert paired.launch.call_args.kwargs == {"workdir": None, "dry_run": False}


def test_uncombinable_network_stops_before_the_server_starts(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paired = _ServerRun(
        mocker, tmp_path, monkeypatch, config='agent = "paired"\nnetwork = "host"\n'
    )
    assert paired.run() == 1
    assert capsys.readouterr().err.strip() == (
        '[network] "host" cannot be combined with a server\'s network; agent '
        '"paired" is paired with server "srv"'
    )
    paired.launch.assert_not_called()


def test_unpaired_client_may_use_the_host_network(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unpaired = _ServerRun(
        mocker, tmp_path, monkeypatch, config=_UNPAIRED + 'network = "host"\n'
    )
    mocker.patch("paddock.__main__._log_network_peers")
    assert unpaired.run() == 0


def test_launch_failure_exits_one_before_paddock_dir(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = mocker.spy(ProjectDirManager, "__enter__")
    paired = _ServerRun(mocker, tmp_path, monkeypatch)
    paired.launch.side_effect = PaddockEnvironmentError("[agent.server] nope")
    assert paired.run() == 1
    assert capsys.readouterr().err.strip() == "[agent.server] nope"
    entered.assert_not_called()
    paired.docker.assert_not_called()


def test_old_docker_stops_a_paired_run_before_launch(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paired = _ServerRun(mocker, tmp_path, monkeypatch)
    paired.version.side_effect = PaddockEnvironmentError("[docker] too old")
    assert paired.run() == 1
    assert capsys.readouterr().err.strip() == "[docker] too old"
    paired.launch.assert_not_called()


def test_old_docker_stops_an_unpaired_server_run_too(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unpaired = _ServerRun(mocker, tmp_path, monkeypatch, config=_UNPAIRED)
    unpaired.version.side_effect = PaddockEnvironmentError("[docker] too old")
    assert unpaired.run() == 1
    unpaired.launch.assert_not_called()


def test_a_run_without_a_server_skips_the_version_check(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = _ServerRun(mocker, tmp_path, monkeypatch, config='agent = "plain"\n')
    assert plain.run() == 0
    plain.version.assert_not_called()
    plain.launch.assert_not_called()
    assert plain.docker.call_args.args[0][-2:] == ["img", "paired"]


def test_dry_run_launches_with_dry_run(
    capsys: pytest.CaptureFixture[str],
    mocker: MockerFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = LaunchResult(_CONNECTION, False, False, _SERVER_ARGV)
    paired = _ServerRun(mocker, tmp_path, monkeypatch, result=result)
    assert paired.run("--dry-run") == 0
    assert paired.launch.call_args.kwargs == {"workdir": None, "dry_run": True}
    paired.version.assert_called_once()
    paired.docker.assert_not_called()
    assert len(capsys.readouterr().out.splitlines()) == 2
