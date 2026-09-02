from pathlib import Path

import pytest

from paddock.__main__ import run


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


def test_dry_run_exits_zero(capsys, minimal_config: Path, mocker, monkeypatch):
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


def test_quiet_suppresses_all_output(capsys, minimal_config: Path, mocker, monkeypatch):
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


def test_missing_image_exits_one(monkeypatch, tmp_path: Path):
    """Missing required 'image' config exits with code 1."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1


def test_runs_docker(minimal_config: Path, mocker, monkeypatch):
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


def test_dry_run_skips_image_build(capsys, tmp_path: Path, mocker, monkeypatch):
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
    mock_maybe_build = mocker.patch("paddock.__main__.ImageBuilder.maybe_build")
    with pytest.raises(SystemExit) as exc:
        run(["--dry-run"])
    assert exc.value.code == 0
    mock_maybe_build.assert_not_called()


def test_paddock_dir_not_a_directory_exits_one(capsys, tmp_path: Path, monkeypatch):
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


def test_help_flag(capsys):
    """--help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        run(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_unknown_agent_exits_one(capsys, tmp_path: Path, monkeypatch):
    """An unregistered agent key reports the installed agents and exits 1."""
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
        '[agent] Unknown agent "bogus"; installed agents: claude, false'
    )
    assert not (tmp_path / ".paddock").exists()


def test_relative_workdir_is_resolved(capsys, tmp_path: Path, mocker, monkeypatch):
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


def test_symlinked_workdir_is_resolved(capsys, tmp_path: Path, mocker, monkeypatch):
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


def test_missing_workdir_exits_one(capsys, tmp_path: Path, monkeypatch):
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


def test_workdir_that_is_a_file_exits_one(capsys, tmp_path: Path, monkeypatch):
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


def test_container_exit_status_is_propagated(minimal_config: Path, mocker, monkeypatch):
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
