import logging
import os
import subprocess
import sys
from pathlib import Path

from paddock.agents import BaseAgent, agent_registry
from paddock.cli import parse_args
from paddock.config.loader import ConfigLoader
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
    runner = loader.resolve(parsed, workdir, environ=dict(os.environ))

    if not runner.is_valid():
        for key, errors in runner.errors.items():
            for error in errors:
                print(f"Config error [{key}]: {error}", file=sys.stderr)
        sys.exit(1)

    config = runner.cleaned_data

    agent_key = "false" if config["agent"] is False else str(config["agent"])
    agent: BaseAgent = agent_registry.get(agent_key)

    logger.info("Using image: %s", config["image"])
    logger.info("Agent: %s", config["agent"])
    for host, container in config["volumes"].items():
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

    docker_argv = DockerCommandBuilder(
        config=config,
        agent=agent,
        workdir=workdir,
    ).build(command=parsed.command)

    if not parsed.quiet:
        print(" ".join(docker_argv))

    if parsed.dry_run:
        sys.exit(0)

    subprocess.run(docker_argv)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
