import logging
import os
import subprocess
import sys
from pathlib import Path

from paddock.agents import BaseAgent, agent_registry
from paddock.cli import parse_args
from paddock.config.errors import ConfigError
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


def run(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(parsed.quiet)

    workdir = Path(parsed.workdir) if parsed.workdir else Path.cwd()

    loader = ConfigLoader()
    try:
        resolved = loader.resolve(parsed, workdir, environ=dict(os.environ))
    except* ConfigError as eg:
        for err in eg.exceptions:
            print(str(err), file=sys.stderr)
        sys.exit(1)

    config = resolved.config

    project_dir_volume = None
    paddock_dir_created = False
    manager = ProjectDirManager()
    if resolved.project_toml_enabled:
        try:
            host_path, container_spec, paddock_dir_created = manager.prepare(
                workdir, readonly=resolved.project_dir_readonly
            )
            project_dir_volume = (host_path, container_spec)
        except ConfigError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)

    agent_key = "false" if config["agent"] is False else str(config["agent"])
    agent: BaseAgent = agent_registry.get(agent_key)

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
        build_args = {**agent.get_build_args(), **config["build"].get("args", {})}
        built = builder.maybe_build(
            build_config=config["build"],
            image=config["image"],
            build_args=build_args,
        )
        logger.info("Image build: %s", "triggered" if built else "skipped (up to date)")

    try:
        docker_argv = DockerCommandBuilder(
            config=config,
            agent=agent,
            workdir=workdir,
            project_dir_volume=project_dir_volume,
        ).build(command=parsed.command)

        if not parsed.quiet:
            print(" ".join(docker_argv))

        if parsed.dry_run:
            sys.exit(0)

        subprocess.run(docker_argv)
    finally:
        if resolved.project_toml_enabled:
            manager.cleanup(workdir, created_by_paddock=paddock_dir_created)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
