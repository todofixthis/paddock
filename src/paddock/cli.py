import argparse
from dataclasses import dataclass

_KNOWN_BOOL_FLAGS = frozenset({"--dry-run", "--quiet"})
_KNOWN_VALUE_FLAGS = frozenset(
    {
        "--agent",
        "--build-context",
        "--build-dockerfile",
        "--build-policy",
        "--config-file",
        "--image",
        "--network",
        "--volume",
        "--workdir",
    }
)


@dataclass
class ParsedArgs:
    agent: str | bool | None
    build_args: dict[str, str]
    build_context: str | None
    build_dockerfile: str | None
    build_policy: str | None
    command: list[str]
    config_file: str | None
    dry_run: bool
    image: str | None
    network: str | None
    quiet: bool
    volumes: dict[str, str]
    workdir: str | None


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    """
    Split argv into (paddock_flags, container_command).

    Scans left-to-right collecting known paddock flags. Stops at:
    - '--' (explicit split, consumed): rest becomes the command
    - A non-flag token (positional): this token and everything after become the command

    Unknown flags (starting with '--' but not in the known set) remain in
    paddock_flags so argparse can report them as errors.
    """
    paddock: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]

        if token == "--":
            return paddock, argv[i + 1 :]

        if token in _KNOWN_BOOL_FLAGS:
            paddock.append(token)
            i += 1
            continue

        flag = token.split("=", 1)[0]
        if flag in _KNOWN_VALUE_FLAGS or flag.startswith("--build-args-"):
            paddock.append(token)
            if "=" not in token:
                i += 1
                if i < len(argv):
                    paddock.append(argv[i])
            i += 1
            continue

        if token.startswith("-"):
            # Unknown flag — leave in paddock so argparse exits with an error.
            paddock.append(token)
            i += 1
            continue

        # Positional — this token and everything after is the container command.
        return paddock, argv[i:]

    return paddock, []


def _parse_volume(value: str) -> tuple[str, str]:
    """
    Parse '--volume=/host:/container[:mode]' into (host_path, container_spec).

    Intentionally does not use the Volume filter — the CLI format separates
    host and container paths with ':', whereas TOML stores them as separate fields.
    """
    host, _, rest = value.partition(":")
    return host, rest


def parse_args(argv: list[str]) -> ParsedArgs:
    """
    Parse paddock CLI arguments.

    Stops consuming paddock flags at the first positional arg or '--'. Unknown
    flags before either stop-point are errors. '--' is consumed; everything
    after it becomes the container command, preserving any subsequent '--'.
    """
    paddock_argv, command = _split_argv(argv)

    # Extract --build-args-<key>=<value> entries before argparse sees them.
    build_args: dict[str, str] = {}
    filtered: list[str] = []
    for entry in paddock_argv:
        if entry.startswith("--build-args-") and "=" in entry:
            raw_key, _, val = entry[len("--build-args-") :].partition("=")
            build_args[raw_key.replace("-", "_")] = val
        else:
            filtered.append(entry)

    parser = argparse.ArgumentParser(prog="paddock", add_help=True)
    parser.add_argument("--agent")
    parser.add_argument("--build-context")
    parser.add_argument("--build-dockerfile")
    parser.add_argument("--build-policy")
    parser.add_argument("--config-file")
    parser.add_argument("--dry-run", action="store_true", default=False)
    parser.add_argument("--image")
    parser.add_argument("--network")
    parser.add_argument("--quiet", action="store_true", default=False)
    parser.add_argument("--volume", action="append", default=[])
    parser.add_argument("--workdir")

    namespace = parser.parse_args(filtered)

    volumes: dict[str, str] = {}
    for vol in namespace.volume:
        host, rest = _parse_volume(vol)
        volumes[host] = rest

    return ParsedArgs(
        agent=namespace.agent,
        build_args=build_args,
        build_context=namespace.build_context,
        build_dockerfile=namespace.build_dockerfile,
        build_policy=namespace.build_policy,
        command=command,
        config_file=namespace.config_file,
        dry_run=namespace.dry_run,
        image=namespace.image,
        network=namespace.network,
        quiet=namespace.quiet,
        volumes=volumes,
        workdir=namespace.workdir,
    )
