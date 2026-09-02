import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

from class_registry import RegistryKeyError

from paddock.agents import BaseAgent, agent_registry
from paddock.cli import parse_args
from paddock.config.errors import ConfigError, PaddockEnvironmentError
from paddock.config.loader import ConfigLoader
from paddock.config.project_dir import ProjectDirManager
from paddock.docker.build import ImageBuilder
from paddock.docker.builder import DockerCommandBuilder

logger = logging.getLogger("paddock")


def _setup_logging(quiet: bool) -> None:
    if quiet:
        logging.disable(logging.CRITICAL)
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")


def _log_network_peers(network: str) -> None:
    """Log names of other containers running on the same network."""
    result = subprocess.run(
        ["docker", "ps", "--filter", f"network={network}", "--format={{.Names}}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for name in result.stdout.strip().splitlines():
            logger.info("  - %s", name)


def _resolve_workdir(raw: str | None) -> Path:
    """Resolve the working directory to an absolute real path, or exit 1.

    Resolved once here so the mount, the container name, the ``.paddock``
    lifecycle and the ``[projects]`` lookup all see the same path.

    Args:
        raw: The ``--workdir`` value, or ``None`` for the current directory.

    Returns:
        The resolved working directory.
    """
    workdir = Path(raw).resolve() if raw else Path.cwd().resolve()
    if not workdir.is_dir():
        print(
            f'[workdir] Path "{raw or workdir}" does not exist or is not a directory',
            file=sys.stderr,
        )
        sys.exit(1)
    return workdir


def _resolve_agent(configured: str | bool) -> BaseAgent:
    """Look up the configured agent, or exit 1 naming the installed agents.

    Resolved before the ``.paddock`` directory is created, so a typo in an
    agent key never leaves the filesystem to unwind.

    Args:
        configured: The merged config's ``agent`` value — an agent key, or
            ``False`` for the no-agent shell.

    Returns:
        The registered agent instance.
    """
    agent_key = "false" if configured is False else str(configured)
    try:
        return agent_registry.get(agent_key)
    except RegistryKeyError:
        installed = ", ".join(sorted(str(key) for key in agent_registry))
        print(
            f'[agent] Unknown agent "{agent_key}"; installed agents: {installed}',
            file=sys.stderr,
        )
        sys.exit(1)


def run(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(parsed.quiet)

    workdir = _resolve_workdir(parsed.workdir)

    loader = ConfigLoader()
    try:
        resolved = loader.resolve(parsed, workdir, environ=dict(os.environ))
    except* ConfigError as eg:
        for err in eg.exceptions:
            print(str(err), file=sys.stderr)
        sys.exit(1)

    config = resolved.config
    agent = _resolve_agent(config["agent"])

    try:
        with ProjectDirManager(
            workdir,
            readonly=resolved.project_dir_readonly,
            enabled=resolved.project_toml_enabled,
        ) as project_dir_volume:
            logger.info("Using image: %s", config["image"])
            logger.info("Agent: %s", config["agent"])
            for host, container in config.get("volumes", {}).items():
                logger.info("Mounting %s -> %s", host, container)
            if config.get("network"):
                logger.info("Network: %s", config["network"])
                logger.info("Other containers on this network:")
                _log_network_peers(config["network"])

            if not parsed.dry_run and config.get("build"):
                builder = ImageBuilder()
                build_args = {
                    **agent.get_build_args(),
                    **config["build"].get("args", {}),
                }
                built = builder.maybe_build(
                    build_config=config["build"],
                    image=config["image"],
                    build_args=build_args,
                )
                logger.info(
                    "Image build: %s", "triggered" if built else "skipped (up to date)"
                )

            docker_argv = DockerCommandBuilder(
                config=config,
                agent=agent,
                workdir=workdir,
                project_dir_volume=project_dir_volume,
            ).build(command=parsed.command)

            if not parsed.quiet:
                print(shlex.join(docker_argv))

            if parsed.dry_run:
                sys.exit(0)

            result = subprocess.run(docker_argv)
            sys.exit(result.returncode)
    except PaddockEnvironmentError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
