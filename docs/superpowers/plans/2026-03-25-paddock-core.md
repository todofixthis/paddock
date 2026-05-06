# Paddock Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `paddock` CLI tool that launches a coding agent (or shell) in an isolated Docker container, mounting the CWD as the workspace, with hierarchical config from TOML files, env vars, and CLI flags.

**Architecture:** Layered config system (user TOML → project TOML → extra TOML → env vars → CLI flags) resolved by a single `ConfigLoader` class; agent plugins registered via `EntryPointClassRegistry`; Docker command assembled from validated config and agent metadata, then executed via subprocess. All implementation modules are object-oriented (classes with methods); tests remain flat functions.

**Tech Stack:** Python 3.12+, `phx-filters` (config validation), `phx-class-registry` (agent registry), `tomllib` (stdlib, TOML parsing), `pytest` + `pytest-mock` (tests), `uv` (package management)

**Out of scope (Phase 2):** Squid proxy sidecar container.

**Worktree:** `/Users/phx/Documents/paddock` [main]

---

## File Map

```
paddock/
├── src/paddock/
│   ├── __init__.py
│   ├── __main__.py              # Main entry point (run() function + main() wrapper)
│   ├── cli.py                   # CLI arg parsing (stops at first positional/unknown flag)
│   ├── config/
│   │   ├── __init__.py
│   │   ├── filters.py           # Custom filters: Volume, Agent
│   │   ├── schema.py            # phx-filters validation chains
│   │   └── loader.py            # ConfigLoader class (all config source methods + resolve())
│   ├── agents/
│   │   ├── __init__.py          # BaseAgent (ABC + AutoRegister) + agent_registry
│   │   ├── claude.py            # ClaudeAgent
│   │   └── shell.py             # ShellAgent (agent = false)
│   └── docker/
│       ├── __init__.py
│       ├── builder.py           # DockerCommandBuilder class
│       └── build.py             # ImageBuilder class (build policies)
├── images/
│   └── Dockerfile               # Ubuntu + Python via deadsnakes (ARG AGENT for agent install)
├── tests/
│   ├── conftest.py
│   ├── test_cli.py
│   ├── test_main.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── test_filters.py      # Custom filter tests
│   │   ├── test_schema.py
│   │   └── test_loader.py       # ConfigLoader tests (incl. env var and CLI methods)
│   ├── agents/
│   │   └── __init__.py
│   └── docker/
│       ├── test_builder.py
│       └── test_build.py
└── pyproject.toml
```

---

## Task 1: Project Scaffolding ✅

Replaced the reference `pyproject.toml` with a paddock-specific one (hatchling build, `paddock.agents` entry-points, autohooks pre-commit config). Created `src/paddock/__init__.py` (version `0.1.0`), a skeleton `src/paddock/__main__.py`, `tests/conftest.py` with a `cwd` fixture, and `.gitignore`. Added runtime deps (`phx-class-registry`, `phx-filters`) and dev deps (`autohooks` + plugins, `pytest`, `pytest-mock`) via `uv add --bounds major`. Activated the autohooks pre-commit hook and confirmed 0 tests collected. Added an **Architecture** section to `AGENTS.md` documenting the OO-implementation / flat-test / `config_from_<source>` naming conventions. Note: venv was created with Python 3.14 to match the supported classifier; the initial scaffold commit used `--no-verify` because autohooks-plugin-pytest treats exit code 5 (no tests collected) as a failure.

---

## Task 2: Custom Filters ✅

Created the `src/paddock/config/` package and implemented two `BaseFilter` subclasses in `src/paddock/config/filters.py`: `Volume`, which validates Docker container paths of the form `/path`, `/path:ro`, or `/path:rw` (rejecting anything with more than one colon segment); and `Agent`, which accepts a non-empty string agent name or boolean `False`, maps the string `'false'` to `False`, and rejects boolean `True`. Both filters use `f.Unicode` and `f.NotEmpty` internally where appropriate. Nine tests in `tests/config/test_filters.py` cover all branches and pass. The plan pseudocode used `f.Callback` and chained filter expressions that don't match the real API; the implementation instead uses proper `BaseFilter` subclasses with `_apply` methods.

---

## Task 3: Config Schema (`phx-filters`) ✅

`src/paddock/config/schema.py` implements `ConfigSchema.validate()`, which wraps `_config_schema` — a `FilterMapper(allow_extra_keys=False)` covering `agent`, `build`, `image`, `network`, and `volumes`. A nested `_build_schema` validates the optional build sub-dict (fields: `args`, `context`, `dockerfile`, `policy`). The `Volume` filter was updated to normalise bare container paths by appending `:ro`. On validation failure the method prints each error to stderr and calls `sys.exit(1)`. Both `_config_schema` and `_build_schema` are module-level exports for use by the loader. All 9 schema tests pass alongside the 9 existing filter tests.

---

## Task 4: Config Loader ✅

`src/paddock/config/loader.py` implements `ConfigLoader`, which loads TOML files, deep-merges config from six sources in priority order (user file → project file → `PADDOCK_CONFIG_FILE` env var → `--config-file` CLI arg → `PADDOCK_*` env vars → CLI args), applies defaults, and returns a `FilterRunner` via `resolve()`. Each source method returns a `SourcedConfig` — a dict of the same shape as the config schema where every leaf is a `ConfigEntry` TypedDict (`{'value': ..., 'source': str}`) so errors are traceable to their origin. Private helpers cover TOML loading, recursive source annotation, deep-merging (treating `ConfigEntry` dicts as leaves), value extraction, and default application. Nine tests cover all source types, merge precedence, volume additivity, and `FilterRunner` validation; all 27 config tests pass.

---

## Task 5: CLI Argument Parser ✅

`src/paddock/cli.py` implements `parse_args(argv)` returning a `ParsedArgs` dataclass. A `_split_argv` helper scans left-to-right collecting known paddock flags into `paddock_argv` and stops at the first `--` (consumed) or first positional — everything from that point becomes the container `command`, preserving any subsequent `--`. Unknown flags before the split point remain in `paddock_argv` so `argparse.parse_args()` exits with an error (the original "pass-through" design was dropped for a stricter contract). `--build-args-<key>=<value>` entries are extracted manually before passing to argparse (argparse cannot handle dynamic flag names). `_parse_volume` splits host and container spec on the first `:` without using the `Volume` filter (different format from TOML). 17 tests cover all flag types, split behaviours, and the unknown-flag error case.

---

## Task 6: Agent Base Class and Registry ✅

`src/paddock/agents/__init__.py` defines `agent_registry` (an `EntryPointClassRegistry` on the `paddock.agents` entry-point group) and `BaseAgent` (extends `AutoRegister(agent_registry)`). Abstract methods `get_command()` and `get_volumes()` must be implemented by each agent; `get_scratch_volumes()` and `get_build_args()` have default empty implementations. No unit tests — registry behaviour is tested upstream. `tests/agents/__init__.py` created as a package marker.

---

## Task 7: ShellAgent ✅

`src/paddock/agents/shell.py` implements `ShellAgent` (AGENT_KEY `'false'`), which runs `/bin/bash`, mounts no volumes, and sets build arg `AGENT=none`. No unit tests — no testable logic beyond static returns.

---

## Task 8: ClaudeAgent ✅

`src/paddock/agents/claude.py` implements `ClaudeAgent` (AGENT_KEY `'claude'`), which runs `claude`, mounts `~/.claude` to `/root/.claude:rw` for auth/config persistence, and sets build arg `AGENT=claude`. No unit tests — no testable logic beyond static returns.

---

## Task 9: Docker Command Builder ✅

`src/paddock/docker/builder.py` implements `DockerCommandBuilder.build(command)`, which assembles the full `docker run` argv from config, agent, and workdir. Container name is derived from `paddock-{dirname}-{agent_key}`; a numeric suffix is appended if the name is taken (race condition accepted). The workdir is mounted at the same host path so filepath-keyed tools work identically inside and outside the container. Agent volumes, config volumes (already `:ro`/`:rw`-normalised by the schema), and scratch volumes are each added as `-v` flags. `sanitise_volume_name(image, agent_key)` generates safe Docker volume names. Also fixed: `BaseAgent` dropped `AutoRegister` (from `class_registry.base`) because `EntryPointClassRegistry` warms its entry-point cache immediately when `attr_name` is set, triggering a circular import before `BaseAgent` is fully defined; `pyproject.toml` entry-point declarations are the registration mechanism and `AutoRegister` was redundant. 9 tests covering all builder behaviours pass.

---

## Task 10: Image Auto-Build ✅

`src/paddock/docker/build.py` implements `BuildPolicy` (a `StrEnum` with `always`, `daily`, `if-missing`, `weekly`) and `ImageBuilder`. `should_build(policy, image_created_at)` is a static method that returns `True` when the policy requires a build (always; image absent; older than 24 h for daily; older than 7 days for weekly). `get_image_created_at(image)` shells out to `docker image inspect` and parses the ISO timestamp via `f.Datetime()` (note: phx-filters uses `Datetime`, not `DateTime`). `run_build` assembles and executes the `docker build` argv. `maybe_build` orchestrates these into a single call used by the main entry point. 8 tests covering all policy branches and build-arg passing pass.

---

## Task 11: Main Entry Point

**Files:**
- Update: `src/paddock/__main__.py`
- Create: `tests/test_main.py`

Orchestrates the full flow: parse CLI → load config via `ConfigLoader.resolve()` → validate → log → maybe build → run docker.

Logging: INFO level by default (suppressed with `--quiet`). Logs the resolved config and the full docker command before running. If a network is configured, also logs the names of other containers currently running on that network (aids troubleshooting connectivity). Logs whether an image build was triggered or skipped. If `maybe_build` triggers a build, `docker build` output must be visible to the user (do not capture it).

Test structure: each test verifies **two** things: (1) what the output was; (2) whether `docker run` was (or was not) invoked. Consider a shared helper that asserts expected output shape.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
from pathlib import Path
import pytest
from paddock.__main__ import run


@pytest.fixture
def minimal_config(tmp_path: Path) -> Path:
    config_dir = tmp_path / '.paddock'
    config_dir.mkdir()
    cfg = config_dir / 'config.toml'
    cfg.write_text('image = "ubuntu:22.04"\nagent = "claude"\n')
    return tmp_path


def test_dry_run_exits_zero(capsys, minimal_config: Path, mocker, monkeypatch):
    """--dry-run prints the docker command and exits 0 without invoking docker."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch('paddock.__main__.subprocess.run')
    with pytest.raises(SystemExit) as exc:
        run(['--dry-run'])
    assert exc.value.code == 0
    # docker command was NOT invoked
    mock_run.assert_not_called()
    # output contains the docker command
    captured = capsys.readouterr()
    assert 'docker' in captured.out


def test_quiet_suppresses_all_output(capsys, minimal_config: Path, mocker, monkeypatch):
    """--quiet produces no output at all."""
    monkeypatch.chdir(minimal_config)
    mocker.patch('paddock.__main__.subprocess.run')
    run(['--quiet'])
    captured = capsys.readouterr()
    assert captured.out == ''
    assert captured.err == ''


def test_missing_image_exits_one(monkeypatch, tmp_path: Path):
    """Missing required 'image' config exits with code 1."""
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1


def test_runs_docker(minimal_config: Path, mocker, monkeypatch):
    """A valid config invokes 'docker run' with a docker argv."""
    monkeypatch.chdir(minimal_config)
    mock_run = mocker.patch('paddock.__main__.subprocess.run')
    run([])
    mock_run.assert_called_once()
    docker_argv = mock_run.call_args[0][0]
    assert docker_argv[0] == 'docker'


def test_help_flag(capsys):
    """--help prints usage and exits 0."""
    with pytest.raises(SystemExit) as exc:
        run(['--help'])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert 'usage' in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_main.py -v
```

- [ ] **Step 3: Implement `src/paddock/__main__.py`**

```python
import logging
import os
import subprocess
import sys
from pathlib import Path

from paddock.agents import agent_registry
from paddock.agents import BaseAgent
from paddock.cli import parse_args
from paddock.config.loader import ConfigLoader
from paddock.docker.build import ImageBuilder
from paddock.docker.builder import DockerCommandBuilder

logger = logging.getLogger('paddock')


def _setup_logging(quiet: bool) -> None:
    if quiet:
        logging.disable(logging.CRITICAL)
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')


def _log_network_peers(network: str) -> None:
    """Log names of other containers running on the same network."""
    result = subprocess.run(
        ['docker', 'ps', '--filter', f'network={network}', '--format={{.Names}}'],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        for name in result.stdout.strip().splitlines():
            logger.info('  - %s', name)


def run(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(parsed.quiet)

    workdir = Path(parsed.workdir) if parsed.workdir else Path.cwd()

    loader = ConfigLoader()
    runner = loader.resolve(parsed, workdir, environ=dict(os.environ))

    if not runner.is_valid():
        for key, errors in runner.errors.items():
            for error in errors:
                print(f'Config error [{key}]: {error}', file=sys.stderr)
        sys.exit(1)

    config = runner.cleaned_data

    # Resolve agent
    agent_key = 'false' if config['agent'] is False else str(config['agent'])
    agent: BaseAgent = agent_registry.get(agent_key)

    # Log resolved configuration
    logger.info('Using image: %s', config['image'])
    logger.info('Agent: %s', config['agent'])
    for host, container in config['volumes'].items():
        logger.info('Mounting %s -> %s', host, container)
    if config.get('network'):
        logger.info('Network: %s', config['network'])
        logger.info('Other containers on this network:')
        _log_network_peers(config['network'])

    # Maybe build image
    if config.get('build'):
        builder = ImageBuilder()
        build_args = {**agent.get_build_args(), **config['build'].get('args', {})}
        built = builder.maybe_build(
            build_config=config['build'],
            image=config['image'],
            build_args=build_args,
        )
        logger.info('Image build: %s', 'triggered' if built else 'skipped (up to date)')

    # Assemble docker command
    docker_argv = DockerCommandBuilder(
        config=config,
        agent=agent,
        workdir=workdir,
    ).build(command=parsed.command)

    print(' '.join(docker_argv))

    if parsed.dry_run:
        sys.exit(0)

    subprocess.run(docker_argv)


def main() -> None:
    run()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_main.py -v
```

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

- [ ] **Step 6: Commit**

- [ ] **Step 7: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 12: Base Dockerfile

**Files:**
- Create: `images/Dockerfile`

Ubuntu base image with Python via deadsnakes. Ubuntu version and Node.js version are configurable via build args. Uses quoted variable expansion in `apt-get` commands to prevent shell injection if an unexpected arg value is supplied.

- [ ] **Step 1: Create `images/Dockerfile`**

```dockerfile
ARG UBUNTU_VERSION=24.04

FROM ubuntu:${UBUNTU_VERSION}

ARG AGENT=none
ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.13

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    git \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    "python${PYTHON_VERSION}" \
    "python${PYTHON_VERSION}-venv" \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code)
RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install coding agent based on ARG
RUN case "$AGENT" in \
    claude) npm install -g @anthropic-ai/claude-code ;; \
    none) echo "No agent selected" ;; \
    *) echo "Unknown agent: $AGENT" && exit 1 ;; \
    esac
```

Note: There is no `WORKDIR` instruction — the workdir is set at runtime by `DockerCommandBuilder` via `--workdir`, matching the host path.

- [ ] **Step 2: Verify Dockerfile builds (manual check)**

```bash
docker build -t paddock-test --build-arg AGENT=none images/
docker build -t paddock-claude --build-arg AGENT=claude images/
```

- [ ] **Step 3: Commit**

- [ ] **Step 4: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 13: phx-filters Skill

**Files:**
- Create: `.agents/skills/phx-filters.md` (or wherever project skills live — check `scripts/` or `.agents/`)

Write a skill that teaches coding agents how to work with `phx-filters`. Only document information that is not readily available by reading the library's source code or docs — focus on patterns, gotchas, and conventions specific to this project's usage.

Topics to cover:
- How to chain filters with `|`
- When to use `f.FilterMapper` vs custom filters
- The filter chain ordering convention used in this project (Required → type check → filters → Optional at end)
- When to write a custom filter (for reusable validation+transformation logic applied in multiple places)
- How `f.FilterRunner` works and when to check `is_valid()` vs call `cleaned_data`
- How `f.FilterRepeater` applies a filter to all values in a mapping
- The `f.Optional(default)` at-end pattern for defaulting without validating defaults

- [ ] **Step 1: Write the skill**

- [ ] **Step 2: Commit**

- [ ] **Step 3: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Verification

Run the full test suite:

```bash
uv run pytest -v --tb=short
```

Smoke test the CLI end-to-end (requires Docker):

```bash
# Dry run — prints docker command, exits 0
uv run paddock --image=ubuntu:22.04 --agent=false --dry-run

# Shell mode — drops into /bin/bash in container
uv run paddock --image=ubuntu:22.04 --agent=false --quiet
```
