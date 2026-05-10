from pathlib import Path

import pytest

from paddock.__main__ import run


@pytest.fixture
def minimal_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / ".paddock"
    config_dir.mkdir()
    cfg = config_dir / "config.toml"
    cfg.write_text('image = "ubuntu:22.04"\nagent = "claude"\n')
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
    mocker.patch("paddock.__main__.subprocess.run")
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    run(["--quiet"])
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
    mocker.patch(
        "paddock.docker.builder.DockerCommandBuilder._container_name_available",
        return_value=True,
    )
    run([])
    mock_run.assert_called_once()
    docker_argv = mock_run.call_args[0][0]
    assert docker_argv[0] == "docker"


def test_dry_run_skips_image_build(capsys, tmp_path: Path, mocker, monkeypatch):
    """--dry-run must not trigger an image build even when build config is present."""
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM ubuntu:22.04\n")
    config_dir = tmp_path / ".paddock"
    config_dir.mkdir()
    cfg = config_dir / "config.toml"
    cfg.write_text(
        f'image = "myimage:latest"\nagent = "claude"\n\n'
        f'[build]\ndockerfile = "{dockerfile}"\n'
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


def test_help_flag(capsys):
    """--help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        run(["--help"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()
