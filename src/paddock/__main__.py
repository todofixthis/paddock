import logging
import os
import shlex
import subprocess
import sys
from pathlib import Path

from class_registry.base import BaseRegistry

from paddock.agents import BaseAgent, agent_registry
from paddock.agents.errors import AgentError
from paddock.agents.pairing import AgentPairing
from paddock.agents.servers import ServerConnection, server_registry
from paddock.cli import parse_args
from paddock.config.errors import ConfigError, PaddockEnvironmentError
from paddock.config.loader import ConfigLoader, ResolvedConfig
from paddock.config.project_dir import ProjectDirManager
from paddock.docker.builder import DockerCommandBuilder
from paddock.docker.factory import ImageSourceFactory
from paddock.docker.server import ServerLauncher
from paddock.docker.version import DockerVersion

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


def _resolve_pairing(
    agent_key: str,
    server_key: str | None,
    *,
    agents: BaseRegistry = agent_registry,
    servers: BaseRegistry = server_registry,
) -> AgentPairing:
    """Resolve the chosen client and server, or exit 1 saying why not.

    Resolved before the ``.paddock`` directory is created, so a typo in an
    agent key never leaves the filesystem to unwind.

    Args:
        agent_key: The chosen client's registry key, from the resolved config.
        server_key: The chosen server's registry key, or ``None`` for none.
        agents: The registry of clients.
        servers: The registry of servers.

    Returns:
        The pairing, with both halves instantiated.
    """
    try:
        return AgentPairing.resolve(
            agent_key, server_key, agents=agents, servers=servers
        )
    except AgentError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _start_server(
    pairing: AgentPairing,
    resolved: ResolvedConfig,
    workdir: Path,
    *,
    dry_run: bool,
    quiet: bool,
) -> ServerConnection | None:
    """Make the chosen server available before the client starts (ADR 019).

    Every check runs before the server is started, and the server before
    ``.paddock`` is created.

    Args:
        pairing: The chosen client and server.
        resolved: The resolved config.
        workdir: The run's workdir.
        dry_run: Check everything, but start nothing.
        quiet: Suppress the server's ``docker run`` line.

    Returns:
        The connection for a paired client; ``None`` with no server, or for a
        client chosen beside a server it does not speak to.

    Raises:
        PaddockEnvironmentError: If the server cannot be used.
    """
    server = pairing.server
    if server is None:
        return None
    key = server.SERVER_KEY
    if pairing.is_paired:
        DockerCommandBuilder.check_paired_network(
            resolved.config.get("network"),
            agent_key=resolved.agent_key,
            server_key=key,
        )
    DockerVersion.require_minimum()

    # The loader resolves settings for every installed server it is given, and
    # the pairing came from the same registry.
    assert resolved.server_settings is not None
    launcher = ServerLauncher(server, resolved.server_settings, environ=os.environ)
    needs_workdir = pairing.is_paired and server.REQUIRES_WORKDIR_MOUNT
    result = launcher.launch(
        workdir=workdir if needs_workdir else None, dry_run=dry_run
    )

    if result.run_argv is not None and not quiet:
        print(shlex.join(result.run_argv))
    if result.drifted:
        logger.warning(
            'Server "%s" is running with settings that differ from your '
            "config; they apply when it is recreated: docker rm -f "
            "paddock-server-%s",
            key,
            key,
        )
    if not pairing.is_paired:
        logger.info(
            'Server: %s (not connected: agent "%s" speaks no server protocol)',
            key,
            resolved.agent_key,
        )
        return None
    logger.info("Server: %s (%s)", key, result.connection.host_url)
    return result.connection


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


def run(
    argv: list[str] | None = None,
    *,
    agents: BaseRegistry = agent_registry,
    servers: BaseRegistry = server_registry,
) -> None:
    """Run paddock.

    Args:
        argv: The command line, or ``None`` for the process's own.
        agents: The registry of clients.
        servers: The registry of servers.
    """
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(parsed.quiet)

    workdir = _resolve_workdir(parsed.workdir)

    loader = ConfigLoader(agents=agents, servers=servers)
    try:
        resolved = loader.resolve(parsed, workdir, environ=dict(os.environ))
    except* ConfigError as eg:
        for err in eg.exceptions:
            print(str(err), file=sys.stderr)
        sys.exit(1)

    config = resolved.config
    pairing = _resolve_pairing(
        resolved.agent_key, resolved.server_key, agents=agents, servers=servers
    )
    agent = pairing.client

    try:
        connection = _start_server(
            pairing, resolved, workdir, dry_run=parsed.dry_run, quiet=parsed.quiet
        )
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
                connection=connection,
            )
            logger.info("Using image: %s", config["image"])
            logger.info("Agent: %s", resolved.agent_key)
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
                agent_args=[*resolved.extra_args, *parsed.agent_args],
            )

            if not parsed.quiet:
                print(shlex.join(docker_argv))

            if parsed.dry_run:
                sys.exit(0)

            result = subprocess.run(
                docker_argv, env={**os.environ, **command_builder.environment}
            )
            sys.exit(result.returncode)
    except PaddockEnvironmentError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def main() -> None:
    run()


if __name__ == "__main__":
    main()
