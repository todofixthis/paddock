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
from paddock.docker.builder import DockerCommandBuilder
from paddock.docker.factory import ImageSourceFactory

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


def _agent_key(configured: str | bool) -> str:
    """Return the registry key for the merged config's ``agent`` value.

    Args:
        configured: An agent key, or ``False`` for the no-agent shell.

    Returns:
        The key the agent is registered under; ``"false"`` for the shell.
    """
    return "false" if configured is False else str(configured)


def _installed_agents() -> str:
    """List the registered agent keys for a message, sorted and comma-joined."""
    return ", ".join(sorted(str(key) for key in agent_registry))


def _extra_args(config: dict, agent_key: str) -> list[str]:
    """Return the configured ``extra_args`` for one agent (ADR 017).

    Args:
        config: The merged config.
        agent_key: The chosen agent's registry key.

    Returns:
        The arguments to place after the agent's command and before the
        command line's own; empty when the agent has none configured.
    """
    return config.get("agents", {}).get(agent_key, {}).get("extra_args", [])


def _warn_unknown_agent_settings(config: dict) -> None:
    """Warn about ``agents`` entries that name no installed agent.

    A warning, not an error, so a config shared between machines still
    loads where a plugin's agent is missing (ADR 017).

    Args:
        config: The merged config.
    """
    for name in sorted(config.get("agents", {})):
        if name not in agent_registry:
            logger.warning(
                '[agents.%s] No agent named "%s" is installed, so its settings '
                "are ignored; installed agents: %s",
                name,
                name,
                _installed_agents(),
            )


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
    agent_key = _agent_key(configured)
    try:
        return agent_registry.get(agent_key)
    except RegistryKeyError:
        print(
            f'[agent] Unknown agent "{agent_key}"; '
            f"installed agents: {_installed_agents()}",
            file=sys.stderr,
        )
        sys.exit(1)


def _prepare_image(config: dict, agent: BaseAgent) -> None:
    """Build or pull the image as ``build.policy`` requires, or exit.

    A failed build or pull exits with Docker's status, Docker having already
    printed why.

    Args:
        config: The merged config; must contain ``build``.
        agent: The resolved agent, whose build args a build passes.
    """
    source = ImageSourceFactory.from_config(
        config["build"], agent_build_args=agent.get_build_args(), environ=os.environ
    )
    try:
        refreshed = source.refresh(config["image"])
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
    outcome = "triggered" if refreshed else "skipped (up to date)"
    logger.info("Image %s: %s", source.action, outcome)


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
    _warn_unknown_agent_settings(config)

    try:
        with ProjectDirManager(
            workdir,
            readonly=resolved.project_dir_readonly,
            enabled=resolved.project_toml_enabled,
        ) as project_dir_volume:
            command_builder = DockerCommandBuilder(
                config=config,
                agent=agent,
                workdir=workdir,
                project_dir_volume=project_dir_volume,
            )
            logger.info("Using image: %s", config["image"])
            logger.info("Agent: %s", config["agent"])
            for host_or_name, container_spec in command_builder.volumes:
                logger.info("Mounting %s -> %s", host_or_name, container_spec)
            if config.get("network"):
                logger.info("Network: %s", config["network"])
                logger.info("Other containers on this network:")
                _log_network_peers(config["network"])

            if not parsed.dry_run and config.get("build"):
                _prepare_image(config, agent)

            docker_argv = command_builder.build(
                command=parsed.command,
                agent_args=[
                    *_extra_args(config, _agent_key(config["agent"])),
                    *parsed.agent_args,
                ],
            )

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
