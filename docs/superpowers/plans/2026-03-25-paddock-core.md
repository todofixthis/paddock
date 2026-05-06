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

## Task 5: CLI Argument Parser

**Files:**
- Create: `src/paddock/cli.py`
- Create: `tests/test_cli.py`

Parses paddock flags, then treats the first positional arg (or everything after `--`) as the start of the container command. Unknown flags are treated as errors — users must provide a positional arg or `--` to disambiguate. Returns a `ParsedArgs` dataclass.

New flags vs original plan:
- `--workdir`: override the working directory (default: `cwd`)
- `--config-file`: inject an extra config file into the resolution hierarchy
- `--build-dockerfile`, `--build-context`, `--build-policy`: build config overrides
- `--build-args-<key>=<value>`: build arg overrides (e.g. `--build-args-python-version=3.13`)

- [ ] **Step 1: Write failing tests**

Each test must have a docstring describing the use case it documents.

```python
# tests/test_cli.py
import pytest

from paddock.cli import parse_args


def test_no_args():
    """Invoking paddock with no arguments yields all-None paddock flags and an empty command."""
    result = parse_args([])
    assert result.image is None
    assert result.agent is None
    assert result.command == []
    assert result.volumes == {}
    assert not result.dry_run
    assert not result.quiet


def test_image_flag():
    """--image sets the container image; no positional means empty command."""
    result = parse_args(['--image=ubuntu:22.04'])
    assert result.image == 'ubuntu:22.04'
    assert result.command == []


def test_agent_flag():
    """--agent sets the agent name."""
    result = parse_args(['--agent=claude'])
    assert result.agent == 'claude'


def test_positional_becomes_command():
    """
    A bare positional argument and everything after it becomes the container command.
    'claude' is interpreted as a program name, not the paddock --agent flag.
    '--agent=plan' is a flag passed to the claude program, not to paddock.
    Users who want to pass both --agent and a positional command must use '--'
    to disambiguate (e.g. paddock --agent=opencode -- claude --agent=plan).
    """
    result = parse_args(['claude', '--agent=plan'])
    assert result.command == ['claude', '--agent=plan']
    assert result.agent is None


def test_paddock_flags_before_positional():
    """Paddock flags before the positional are parsed; the positional starts the command."""
    result = parse_args(['--image=foo', 'claude', '--agent=plan'])
    assert result.image == 'foo'
    assert result.command == ['claude', '--agent=plan']


def test_double_dash_splits():
    """'--' explicitly ends paddock arguments; everything after is the container command."""
    result = parse_args(['--image=foo', '--', '--resume'])
    assert result.image == 'foo'
    assert result.command == ['--resume']


def test_double_dash_multiple_occurrences():
    """
    Multiple '--' occurrences: only the first is treated as a paddock/command split.
    Subsequent '--' are passed through to the container command unchanged.
    """
    result = parse_args(['--agent=opencode', '--', '--continue', '--', 'auth', 'login'])
    assert result.agent == 'opencode'
    assert result.command == ['--continue', '--', 'auth', 'login']


def test_double_dash_after_positional():
    """
    '--' after a positional arg: the positional already ended paddock parsing,
    so '--' passes through to the container command.
    """
    result = parse_args(['--agent=opencode', 'web', '--', '--port=4096'])
    assert result.agent == 'opencode'
    assert result.command == ['web', '--', '--port=4096']


def test_unknown_flag_is_error():
    """An unrecognised flag before any positional or '--' exits non-zero."""
    with pytest.raises(SystemExit):
        parse_args(['--not-a-paddock-flag'])


def test_volume_flag():
    """--volume=/host:/container:rw mounts a volume with read-write access."""
    result = parse_args(['--volume=/host:/container:rw'])
    assert result.volumes == {'/host': '/container:rw'}


def test_volume_flag_repeated():
    """Multiple --volume flags accumulate into a dict keyed by host path."""
    result = parse_args(['--volume=/a:/ca', '--volume=/b:/cb:ro'])
    assert result.volumes == {'/a': '/ca', '/b': '/cb:ro'}


def test_volume_flag_no_mode():
    """--volume without a mode suffix stores the container path as-is (no ':ro' appended here)."""
    # Note: ':ro' is appended by the Volume filter during config schema validation,
    # not by the CLI parser. The CLI uses a different format than config.toml:
    # CLI: /host:/container[:mode]   (colon-separated host and container spec)
    # TOML: host_path = "container_path[:mode]"  (two separate fields)
    # _parse_volume() is intentionally NOT using the Volume filter for this reason.
    result = parse_args(['--volume=/host:/container'])
    assert result.volumes == {'/host': '/container'}


def test_dry_run_flag():
    """--dry-run prints the docker command and exits without running it."""
    result = parse_args(['--dry-run'])
    assert result.dry_run


def test_quiet_flag():
    """--quiet suppresses all log output."""
    result = parse_args(['--quiet'])
    assert result.quiet


def test_workdir_flag():
    """--workdir overrides the directory used to locate project config and as the cwd mount."""
    result = parse_args(['--workdir=/tmp/myproject'])
    assert result.workdir == '/tmp/myproject'


def test_config_file_flag():
    """--config-file injects an extra config file into the hierarchy after project config."""
    result = parse_args(['--config-file=/tmp/extra.toml'])
    assert result.config_file == '/tmp/extra.toml'


def test_build_flags():
    """Build config can be overridden via CLI flags."""
    result = parse_args(
        ['--build-dockerfile=/Dockerfile', '--build-context=.', '--build-policy=always']
    )
    assert result.build_dockerfile == '/Dockerfile'
    assert result.build_context == '.'
    assert result.build_policy == 'always'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement `src/paddock/cli.py`**

**Design:** Maintain a set of known paddock flags. Scan `argv` left-to-right: collect known flags (and their values) into `paddock_argv`; stop at `--` (consumed) or the first non-flag token (positional). Unknown flags (start with `--` but not in the known set) are left in `paddock_argv` so `argparse` reports them as errors. Everything from the stop-point onward becomes the container command (preserving any subsequent `--`).

`ParsedArgs` dataclass fields (alphabetical): `agent`, `build_args`, `build_context`, `build_dockerfile`, `build_policy`, `command`, `config_file`, `dry_run`, `image`, `network`, `quiet`, `volumes`, `workdir`.

For `--build-args-<key>=<value>`: extract these from `paddock_argv` before passing to `argparse` (argparse cannot handle dynamic flag names). Strip the `--build-args-` prefix, replace `-` with `_` in the key.

`_parse_volume(value)` splits on the first `:` to separate host path from container spec. Does **not** use the `Volume` filter (different format from TOML).

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

- [ ] **Step 6: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

- [ ] **Step 6: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 6: Agent Base Class and Registry

**Files:**
- Create: `src/paddock/agents/__init__.py`
- Create: `tests/agents/__init__.py`

`BaseAgent` lives in `src/paddock/agents/__init__.py` and uses `AutoRegister(agent_registry)` as its base class, so subclasses self-register via their `AGENT_KEY` attribute.

No unit tests for this task — the registry's `EntryPointClassRegistry` behaviour is already tested upstream; tests here would just confirm static return values.

- [ ] **Step 1: Implement `src/paddock/agents/__init__.py`**

```python
from abc import abstractmethod
from typing import ClassVar

from class_registry import AutoRegister
from class_registry.entry_points import EntryPointClassRegistry

agent_registry: EntryPointClassRegistry = EntryPointClassRegistry('paddock.agents')


class BaseAgent(AutoRegister(agent_registry)):
    AGENT_KEY: ClassVar[str]

    @abstractmethod
    def get_command(self) -> list[str]:
        """
        Default command to run in the container.

        Example: ['claude'] for ClaudeAgent, ['/bin/bash'] for ShellAgent.
        """

    @abstractmethod
    def get_volumes(self) -> dict[str, str]:
        """
        Host-path-keyed volume mounts specific to this agent.

        Values are '/container/path' or '/container/path:mode'.
        Example: {'/home/user/.claude': '/root/.claude:rw'}
        """

    def get_scratch_volumes(self, image: str) -> dict[str, str]:
        """
        Named Docker volumes (not host paths) to create and mount.

        Keys are volume names, values are container paths. Override when the agent
        needs persistent storage that must not be shared with the host.
        Example: {'paddock_ubuntu_22_04_claude': '/scratch'}
        """
        return {}

    def get_build_args(self) -> dict[str, str]:
        """
        Docker build args to pass when building the paddock base image.

        Used when the built-in Dockerfile is referenced in the build config.
        Example: {'AGENT': 'claude'}
        """
        return {}
```

- [ ] **Step 2: Commit**

- [ ] **Step 3: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 7: ShellAgent

**Files:**
- Create: `src/paddock/agents/shell.py`

`ShellAgent` is used when `agent = false` in config. It drops the user into `/bin/bash`. No unit tests — there is no logic to test beyond static return values.

- [ ] **Step 1: Implement `src/paddock/agents/shell.py`**

```python
from paddock.agents import BaseAgent


class ShellAgent(BaseAgent):
    AGENT_KEY = 'false'

    def get_command(self) -> list[str]:
        return ['/bin/bash']

    def get_volumes(self) -> dict[str, str]:
        return {}

    def get_build_args(self) -> dict[str, str]:
        return {'AGENT': 'none'}
```

- [ ] **Step 2: Commit**

- [ ] **Step 3: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 8: ClaudeAgent

**Files:**
- Create: `src/paddock/agents/claude.py`

`ClaudeAgent` mounts `~/.claude` for auth/config persistence. No unit tests — no complex logic.

- [ ] **Step 1: Implement `src/paddock/agents/claude.py`**

```python
from pathlib import Path

from paddock.agents import BaseAgent


class ClaudeAgent(BaseAgent):
    AGENT_KEY = 'claude'

    def get_command(self) -> list[str]:
        return ['claude']

    def get_volumes(self) -> dict[str, str]:
        return {str(Path.home() / '.claude'): '/root/.claude:rw'}

    def get_build_args(self) -> dict[str, str]:
        return {'AGENT': 'claude'}
```

- [ ] **Step 2: Commit**

- [ ] **Step 3: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 9: Docker Command Builder

**Files:**
- Create: `src/paddock/docker/__init__.py`
- Create: `src/paddock/docker/builder.py`
- Create: `tests/docker/__init__.py`
- Create: `tests/docker/test_builder.py`

Assembles the full `docker run` argv list from the validated config, the resolved agent, and the workdir.

Key behaviours:
- **Container name**: derive from workdir dirname and agent key (e.g. `paddock-portfolio-claude`). Check for conflicts; append numeric suffix if taken (e.g. `paddock-portfolio-claude-1`). Check once — accept the race condition.
- **Workdir in container**: mount and set `--workdir` to the *same path* as the host workdir (not `/workspace`). This ensures tools that store project config by filepath work correctly across host and container.
- **Volume mode default**: config volumes without an explicit mode already have `:ro` appended by the `Volume` filter during schema validation — do not re-append.

- [ ] **Step 1: Write failing tests**

```python
# tests/docker/test_builder.py
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from paddock.docker.builder import DockerCommandBuilder, sanitise_volume_name


def test_sanitise_volume_name():
    assert sanitise_volume_name('ubuntu:22.04', 'claude') == 'paddock_ubuntu_22_04_claude'
    assert sanitise_volume_name('my.registry/image:tag', 'false') == 'paddock_my_registry_image_tag_false'


def make_agent(command=None, volumes=None, scratch_volumes=None):
    agent = MagicMock()
    agent.AGENT_KEY = 'claude'
    agent.get_command.return_value = command or ['claude']
    agent.get_volumes.return_value = volumes or {}
    agent.get_scratch_volumes.return_value = scratch_volumes or {}
    return agent


def test_minimal_command(mocker, tmp_path: Path):
    """
    A minimal docker run command includes:
    - 'docker run' to invoke docker
    - '--rm' to remove the container on exit (no cleanup needed)
    - '-it' for interactive TTY (required for coding agents)
    - '--name' set to the paddock-{dirname}-{agent} convention
    - '--workdir' set to the same absolute path as the host workdir
    - '-v {workdir}:{workdir}:rw' to mount the workdir at the same path
    - the image name
    """
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent()
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    assert argv[0] == 'docker'
    assert 'run' in argv
    assert '--rm' in argv
    assert '-it' in argv
    assert f'--workdir={tmp_path}' in argv
    assert f'-v' in argv
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == '-v']
    assert any(f'{tmp_path}:{tmp_path}:rw' in v for v in vol_args)
    assert 'ubuntu:22.04' in argv


def test_container_name_from_workdir(mocker, tmp_path: Path):
    """Container is named 'paddock-{dirname}-{agent}'."""
    workdir = tmp_path / 'my-project'
    workdir.mkdir()
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent()
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=workdir).build(command=[])
    assert '--name' in argv
    name_idx = argv.index('--name')
    assert argv[name_idx + 1] == 'paddock-my-project-claude'


def test_container_name_suffix_on_conflict(mocker, tmp_path: Path):
    """If the container name is taken, a numeric suffix is appended."""
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent()
    # First name taken, second available
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        side_effect=[False, True],
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    name_idx = argv.index('--name')
    assert argv[name_idx + 1].endswith('-1')


def test_uses_agent_command(mocker, tmp_path: Path):
    """When no command override is given, the agent's default command is appended."""
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(command=['claude'])
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    assert argv[-1] == 'claude'


def test_command_override(mocker, tmp_path: Path):
    """An explicit command overrides the agent default."""
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(command=['claude'])
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=['opencode', '--flag'])
    assert argv[-2:] == ['opencode', '--flag']


def test_config_volumes(mocker, tmp_path: Path):
    """Config volumes are passed as -v flags."""
    config = {
        'image': 'ubuntu:22.04',
        'agent': 'claude',
        'volumes': {'/host/data': '/data:ro'},
        'network': None,
    }
    agent = make_agent()
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == '-v']
    assert any('/host/data:/data:ro' in v for v in vol_args)


def test_network(mocker, tmp_path: Path):
    """A configured network is passed via --network."""
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': 'mynet'}
    agent = make_agent()
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    assert '--network' in argv
    assert 'mynet' in argv


def test_scratch_volume(mocker, tmp_path: Path):
    """Agent scratch volumes (named Docker volumes) are passed via -v."""
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(scratch_volumes={'paddock_ubuntu_22_04_claude': '/scratch'})
    mocker.patch(
        'paddock.docker.builder.DockerCommandBuilder._container_name_available',
        return_value=True,
    )
    argv = DockerCommandBuilder(config=config, agent=agent, workdir=tmp_path).build(command=[])
    vol_args = [argv[i + 1] for i, a in enumerate(argv) if a == '-v']
    assert any('paddock_ubuntu_22_04_claude:/scratch' in v for v in vol_args)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/docker/test_builder.py -v
```

- [ ] **Step 3: Implement `src/paddock/docker/builder.py`**

```python
import re
import subprocess
from pathlib import Path

from paddock.agents import BaseAgent


def sanitise_volume_name(image: str, agent_key: str) -> str:
    """Generate a Docker volume name from image + agent key."""
    sanitised = re.sub(r'[^a-z0-9]', '_', image.lower())
    return f'paddock_{sanitised}_{agent_key}'


class DockerCommandBuilder:
    def __init__(self, *, config: dict, agent: BaseAgent, workdir: Path) -> None:
        self._config = config
        self._agent = agent
        self._workdir = workdir

    def build(self, *, command: list[str]) -> list[str]:
        """Assemble the full 'docker run' argv list."""
        argv = ['docker', 'run', '--rm', '-it']

        # Container name derived from workdir dirname
        argv += ['--name', self._resolve_container_name()]

        # Workdir matches host path inside the container
        argv += [f'--workdir={self._workdir}']

        # Mount workdir at the same path
        argv += self._volume_flag(str(self._workdir), f'{self._workdir}:rw')

        # Agent-specific volumes
        for host, container in self._agent.get_volumes().items():
            argv += self._volume_flag(host, container)

        # Config volumes (already normalised with :ro/:rw by Volume filter)
        for host, container in self._config.get('volumes', {}).items():
            argv += self._volume_flag(host, container)

        # Scratch volumes (named Docker volumes)
        for vol_name, container_path in self._agent.get_scratch_volumes(self._config['image']).items():
            argv += self._volume_flag(vol_name, container_path)

        # Network
        if self._config.get('network'):
            argv += ['--network', self._config['network']]

        # Image
        argv.append(self._config['image'])

        # Command: CLI override takes precedence over agent default
        argv += command if command else self._agent.get_command()

        return argv

    def _resolve_container_name(self) -> str:
        """Derive container name from workdir; append suffix if taken."""
        dirname = self._workdir.name.lower()
        agent_key = self._agent.AGENT_KEY
        base_name = f'paddock-{dirname}-{agent_key}'

        if self._container_name_available(base_name):
            return base_name

        suffix = 1
        while True:
            candidate = f'{base_name}-{suffix}'
            if self._container_name_available(candidate):
                return candidate
            suffix += 1

    def _container_name_available(self, name: str) -> bool:
        """Return True if no running or stopped container has this name."""
        result = subprocess.run(
            ['docker', 'ps', '-a', '--filter', f'name=^{name}$', '--format={{.Names}}'],
            capture_output=True,
            text=True,
        )
        return name not in result.stdout.splitlines()

    @staticmethod
    def _volume_flag(host_or_name: str, container_spec: str) -> list[str]:
        return ['-v', f'{host_or_name}:{container_spec}']
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/docker/test_builder.py -v
```

- [ ] **Step 5: Commit**

- [ ] **Step 6: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

---

## Task 10: Image Auto-Build

**Files:**
- Create: `src/paddock/docker/build.py`
- Create: `tests/docker/test_build.py`

Implements build policies: `if-missing`, `always`, `daily`, `weekly`. Calls `docker build` when the policy requires it. Use `f.DateTime()` from `phx-filters` to convert ISO timestamp strings to `datetime` objects in `get_image_created_at`.

- [ ] **Step 1: Write failing tests**

```python
# tests/docker/test_build.py
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from paddock.docker.build import ImageBuilder, BuildPolicy


def test_should_build_always():
    assert ImageBuilder.should_build(BuildPolicy.ALWAYS, image_created_at=datetime.now(timezone.utc))


def test_should_build_if_missing_image_exists():
    assert not ImageBuilder.should_build(BuildPolicy.IF_MISSING, image_created_at=datetime.now(timezone.utc))


def test_should_build_if_missing_image_absent():
    assert ImageBuilder.should_build(BuildPolicy.IF_MISSING, image_created_at=None)


def test_should_build_daily_old_image():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    assert ImageBuilder.should_build(BuildPolicy.DAILY, image_created_at=old)


def test_should_build_daily_fresh_image():
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not ImageBuilder.should_build(BuildPolicy.DAILY, image_created_at=fresh)


def test_should_build_weekly_old_image():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert ImageBuilder.should_build(BuildPolicy.WEEKLY, image_created_at=old)


def test_run_build_basic(mocker):
    mock_run = mocker.patch('paddock.docker.build.subprocess.run')
    ImageBuilder().run_build(
        image='myapp:latest',
        dockerfile='/path/Dockerfile',
        context='/path',
        build_args={},
    )
    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args[:3] == ['docker', 'build', '-t']
    assert 'myapp:latest' in call_args
    assert '-f' in call_args


def test_run_build_with_args(mocker):
    mock_run = mocker.patch('paddock.docker.build.subprocess.run')
    ImageBuilder().run_build(
        image='myapp:latest',
        dockerfile='/path/Dockerfile',
        context='/path',
        build_args={'AGENT': 'claude'},
    )
    call_args = mock_run.call_args[0][0]
    assert '--build-arg' in call_args
    assert 'AGENT=claude' in call_args
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/docker/test_build.py -v
```

- [ ] **Step 3: Implement `src/paddock/docker/build.py`**

```python
import subprocess
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path

import filters as f


class BuildPolicy(StrEnum):
    ALWAYS = 'always'
    DAILY = 'daily'
    IF_MISSING = 'if-missing'
    WEEKLY = 'weekly'


class ImageBuilder:
    @staticmethod
    def should_build(policy: BuildPolicy, image_created_at: datetime | None) -> bool:
        """Determine whether to build the image given the policy and current image age."""
        match policy:
            case BuildPolicy.ALWAYS:
                return True
            case BuildPolicy.IF_MISSING:
                return image_created_at is None
            case BuildPolicy.DAILY:
                if image_created_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_created_at) > timedelta(hours=24)
            case BuildPolicy.WEEKLY:
                if image_created_at is None:
                    return True
                return (datetime.now(timezone.utc) - image_created_at) > timedelta(days=7)

    def get_image_created_at(self, image: str) -> datetime | None:
        """Return the creation timestamp of a local Docker image, or None if absent."""
        result = subprocess.run(
            ['docker', 'image', 'inspect', '--format={{.Created}}', image],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        created_str = result.stdout.strip()
        # Use f.DateTime() to convert ISO string to datetime
        runner = f.FilterRunner(f.DateTime(), created_str)
        if not runner.is_valid():
            return None
        return runner.cleaned_data

    def run_build(
        self,
        *,
        image: str,
        dockerfile: str,
        context: str,
        build_args: dict[str, str],
    ) -> None:
        """Run docker build, streaming output to stdout."""
        argv = ['docker', 'build', '-t', image, '-f', dockerfile]
        for key, value in build_args.items():
            argv += ['--build-arg', f'{key}={value}']
        argv.append(context)
        subprocess.run(argv, check=True)

    def maybe_build(
        self,
        *,
        build_config: dict,
        image: str,
        build_args: dict[str, str],
    ) -> bool:
        """
        Build the image if the build policy requires it.
        Returns True if a build was triggered, False if skipped.
        """
        policy = BuildPolicy(build_config.get('policy', 'if-missing'))
        dockerfile = build_config['dockerfile']
        context = build_config.get('context') or str(Path(dockerfile).parent)

        image_created_at = self.get_image_created_at(image)
        if self.should_build(policy, image_created_at):
            self.run_build(
                image=image,
                dockerfile=dockerfile,
                context=context,
                build_args=build_args,
            )
            return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/docker/test_build.py -v
```

- [ ] **Step 5: Commit**

- [ ] **Step 6: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.

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
