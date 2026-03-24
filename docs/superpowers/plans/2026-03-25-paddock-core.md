# Paddock Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `paddock` CLI tool that launches a coding agent (or shell) in an isolated Docker container, mounting the CWD as the workspace, with hierarchical config from TOML files, env vars, and CLI flags.

**Architecture:** Layered config system (user TOML → project TOML → env vars → CLI flags) validated with `phx-filters`; agent plugins registered via `EntryPointClassRegistry`; Docker command assembled from validated config and agent metadata, then executed via subprocess.

**Tech Stack:** Python 3.12+, `phx-filters` (config validation), `phx-class-registry` (agent registry), `tomllib` (stdlib, TOML parsing), `pytest` + `pytest-mock` (tests), `uv` (package management)

**Out of scope (Phase 2):** Squid proxy sidecar container.

---

## File Map

```
paddock/
├── src/paddock/
│   ├── __init__.py
│   ├── __main__.py          # Orchestration entry point
│   ├── cli.py               # CLI arg parsing (stops at first positional/unknown flag)
│   ├── config/
│   │   ├── __init__.py
│   │   ├── schema.py        # phx-filters validation chains
│   │   ├── loader.py        # Load + deep-merge config from all sources
│   │   └── env.py           # PADDOCK_* env vars → config dict
│   ├── agents/
│   │   ├── __init__.py      # agent_registry = EntryPointClassRegistry(...)
│   │   ├── base.py          # BaseAgent ABC
│   │   ├── claude.py        # ClaudeAgent
│   │   └── shell.py         # ShellAgent (agent = false)
│   └── docker/
│       ├── __init__.py
│       ├── builder.py       # Assembles docker run argv list
│       └── build.py         # Image auto-build logic (build policies)
├── images/
│   └── Dockerfile           # Ubuntu + Python via deadsnakes (ARG AGENT for agent install)
├── tests/
│   ├── conftest.py
│   ├── test_cli.py
│   ├── config/
│   │   ├── test_schema.py
│   │   ├── test_loader.py
│   │   └── test_env.py
│   ├── agents/
│   │   ├── test_claude.py
│   │   └── test_shell.py
│   └── docker/
│       ├── test_builder.py
│       └── test_build.py
└── pyproject.toml
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/paddock/__init__.py`
- Create: `src/paddock/__main__.py` (skeleton)
- Create: `tests/conftest.py`
- Create: `.gitignore`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
build-backend = "hatchling.build"
requires = ["hatchling"]

[project]
dependencies = [
    "phx-class-registry>=4",
    "phx-filters>=3",
]
dynamic = ["version"]
name = "paddock"
requires-python = ">=3.12"

[project.entry-points."paddock.agents"]
claude = "paddock.agents.claude:ClaudeAgent"
false = "paddock.agents.shell:ShellAgent"

[project.scripts]
paddock = "paddock.__main__:main"

[tool.hatch.version]
path = "src/paddock/__init__.py"

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-mock>=3",
]
```

- [ ] **Step 2: Create `src/paddock/__init__.py`**

```python
__version__ = '0.1.0'
```

- [ ] **Step 3: Create `src/paddock/__main__.py` skeleton**

```python
def main() -> None:
    raise NotImplementedError


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import pytest


@pytest.fixture
def cwd(tmp_path):
    """A temporary directory standing in for the current working directory."""
    return tmp_path
```

- [ ] **Step 5: Create `.gitignore`**

```
.python-version
.venv/
__pycache__/
dist/
*.egg-info/
```

- [ ] **Step 6: Install and verify**

```bash
uv sync
uv run pytest  # should collect 0 tests, exit 0
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/ tests/ .gitignore
git commit
```

---

## Task 2: Config Schema (`phx-filters`)

**Files:**
- Create: `src/paddock/config/__init__.py`
- Create: `src/paddock/config/schema.py`
- Create: `tests/config/test_schema.py`

The schema validates the *final merged config dict* after all layers have been applied and defaults set. It does not set defaults — that is the loader's job.

- [ ] **Step 1: Write failing tests**

```python
# tests/config/test_schema.py
import pytest
from paddock.config.schema import validate_config


def test_valid_minimal():
    result = validate_config({'image': 'ubuntu:22.04', 'agent': 'claude'})
    assert result == {'image': 'ubuntu:22.04', 'agent': 'claude', 'build': None, 'volumes': {}, 'network': None}


def test_invalid_empty_image():
    with pytest.raises(SystemExit):
        validate_config({'image': '', 'agent': 'claude'})


def test_invalid_missing_image():
    with pytest.raises(SystemExit):
        validate_config({'agent': 'claude'})


def test_agent_false():
    result = validate_config({'image': 'ubuntu:22.04', 'agent': False})
    assert result['agent'] is False


def test_unknown_key_rejected():
    with pytest.raises(SystemExit):
        validate_config({'image': 'ubuntu:22.04', 'agent': 'claude', 'typo': 'oops'})


def test_valid_build_config():
    config = {
        'image': 'myapp:latest',
        'agent': 'claude',
        'build': {'dockerfile': '/path/to/Dockerfile', 'context': None, 'policy': 'if-missing'},
    }
    result = validate_config(config)
    assert result['build']['policy'] == 'if-missing'


def test_valid_volumes():
    config = {
        'image': 'ubuntu:22.04',
        'agent': 'claude',
        'volumes': {'/host/path': '/container/path', '/other': '/dest:rw'},
    }
    result = validate_config(config)
    assert result['volumes'] == {'/host/path': '/container/path', '/other': '/dest:rw'}


def test_invalid_volume_value():
    with pytest.raises(SystemExit):
        validate_config({
            'image': 'ubuntu:22.04',
            'agent': 'claude',
            'volumes': {'/host': 'not:a:valid:path'},
        })
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/config/test_schema.py -v
# Expected: ImportError or similar
```

- [ ] **Step 3: Implement `src/paddock/config/schema.py`**

```python
import sys

import filters as f

BUILD_POLICIES = ('always', 'daily', 'if-missing', 'weekly')

# Volume value: "/container/path" or "/container/path:ro" or "/container/path:rw"
_volume_value = f.Unicode | f.Regex(r'^[^:]+(:r[ow])?$')

_build_schema = f.FilterMapper(
    {
        'context': f.Optional,
        'dockerfile': f.Required | f.Unicode | f.NotEmpty,
        'policy': f.Optional | f.Choice(BUILD_POLICIES),
    },
    allow_extra_keys=False,
)

_config_schema = f.FilterMapper(
    {
        'agent': f.Required | f.Type((str, bool)),
        'build': f.Optional | _build_schema,
        'image': f.Required | f.Unicode | f.NotEmpty,
        'network': f.Optional,
        'volumes': f.Optional | f.FilterRepeater(_volume_value),
    },
    allow_extra_keys=False,
)


def validate_config(config: dict) -> dict:
    """Validate the merged config dict. Prints errors to stderr and exits 1 on failure."""
    runner = f.FilterRunner(_config_schema, config)
    if runner.is_valid():
        return runner.cleaned_data
    for key, errors in runner.errors.items():
        for error in errors:
            print(f'Config error [{key}]: {error}', file=sys.stderr)
    sys.exit(1)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/config/test_schema.py -v
```

- [ ] **Step 5: Commit**

---

## Task 3: Config Loader

**Files:**
- Create: `src/paddock/config/loader.py`
- Create: `tests/config/test_loader.py`

The loader reads TOML files, deep-merges them (volumes are additive by host path), and applies defaults before validation.

- [ ] **Step 1: Write failing tests**

```python
# tests/config/test_loader.py
from pathlib import Path
import pytest
from paddock.config.loader import load_config_files, merge_configs, apply_defaults


def test_load_missing_files_returns_empty(tmp_path):
    result = load_config_files(
        user_config=tmp_path / 'nonexistent.toml',
        project_config=tmp_path / '.paddock' / 'config.toml',
    )
    assert result == {}


def test_load_user_config(tmp_path):
    cfg = tmp_path / 'config.toml'
    cfg.write_text('image = "ubuntu:22.04"\nagent = "claude"\n')
    result = load_config_files(user_config=cfg, project_config=tmp_path / 'nope.toml')
    assert result == {'image': 'ubuntu:22.04', 'agent': 'claude'}


def test_project_overrides_user(tmp_path):
    user = tmp_path / 'user.toml'
    user.write_text('image = "base:1.0"\nagent = "claude"\n')
    project = tmp_path / 'project.toml'
    project.write_text('image = "project:2.0"\n')
    result = load_config_files(user_config=user, project_config=project)
    assert result['image'] == 'project:2.0'
    assert result['agent'] == 'claude'


def test_volumes_are_additive(tmp_path):
    user = tmp_path / 'user.toml'
    user.write_text('[volumes]\n"/a" = "/ca"\n"/b" = "/cb"\n')
    project = tmp_path / 'project.toml'
    project.write_text('[volumes]\n"/b" = "/cb-override:rw"\n"/c" = "/cc"\n')
    result = load_config_files(user_config=user, project_config=project)
    assert result['volumes'] == {'/a': '/ca', '/b': '/cb-override:rw', '/c': '/cc'}


def test_apply_defaults():
    result = apply_defaults({})
    assert result['agent'] == 'claude'
    assert result['volumes'] == {}
    assert result['build'] is None
    assert result['network'] is None


def test_merge_configs_deep():
    base = {'image': 'base', 'build': {'policy': 'always', 'dockerfile': '/base/Dockerfile'}}
    override = {'build': {'dockerfile': '/new/Dockerfile'}}
    result = merge_configs(base, override)
    assert result['build']['dockerfile'] == '/new/Dockerfile'
    assert result['build']['policy'] == 'always'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/config/test_loader.py -v
```

- [ ] **Step 3: Implement `src/paddock/config/loader.py`**

```python
import tomllib
from pathlib import Path


def load_toml(path: Path) -> dict:
    """Load a TOML file, returning {} if it doesn't exist."""
    if not path.exists():
        return {}
    with path.open('rb') as fh:
        return tomllib.load(fh)


def merge_configs(base: dict, override: dict) -> dict:
    """Deep-merge override into base. Volumes are merged by host path."""
    result = dict(base)
    for key, value in override.items():
        if key == 'volumes' and isinstance(base.get('volumes'), dict) and isinstance(value, dict):
            result['volumes'] = {**base.get('volumes', {}), **value}
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            result[key] = merge_configs(base[key], value)
        else:
            result[key] = value
    return result


def apply_defaults(config: dict) -> dict:
    """Apply default values to a config dict (mutates and returns it)."""
    config.setdefault('agent', 'claude')
    config.setdefault('build', None)
    config.setdefault('network', None)
    config.setdefault('volumes', {})
    if isinstance(config.get('build'), dict):
        config['build'].setdefault('context', None)
        config['build'].setdefault('policy', 'if-missing')
    return config


def load_config_files(user_config: Path, project_config: Path) -> dict:
    """Load and merge user-level and project-level TOML config files."""
    user = load_toml(user_config)
    project = load_toml(project_config)
    return merge_configs(user, project)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/config/test_loader.py -v
```

- [ ] **Step 5: Commit**

---

## Task 4: Env Var Mapper

**Files:**
- Create: `src/paddock/config/env.py`
- Create: `tests/config/test_env.py`

Maps `PADDOCK_*` env vars to a config dict with the same shape as TOML, stripping `None` values so only set vars participate in merging.

- [ ] **Step 1: Write failing tests**

```python
# tests/config/test_env.py
from paddock.config.env import env_to_config


def test_empty_env(monkeypatch):
    monkeypatch.delenv('PADDOCK_IMAGE', raising=False)
    result = env_to_config({})
    assert result == {}


def test_image_override(monkeypatch):
    result = env_to_config({'PADDOCK_IMAGE': 'myimage:latest'})
    assert result == {'image': 'myimage:latest'}


def test_build_dockerfile(monkeypatch):
    result = env_to_config({'PADDOCK_BUILD_DOCKERFILE': '/path/to/Dockerfile'})
    assert result == {'build': {'dockerfile': '/path/to/Dockerfile'}}


def test_multiple_build_vars():
    result = env_to_config({
        'PADDOCK_BUILD_DOCKERFILE': '/Dockerfile',
        'PADDOCK_BUILD_POLICY': 'always',
    })
    assert result == {'build': {'dockerfile': '/Dockerfile', 'policy': 'always'}}


def test_agent_override():
    result = env_to_config({'PADDOCK_AGENT': 'false'})
    # env var is a string; conversion to bool False happens at schema validation
    assert result == {'agent': 'false'}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/config/test_env.py -v
```

- [ ] **Step 3: Implement `src/paddock/config/env.py`**

```python
def env_to_config(environ: dict[str, str]) -> dict:
    """
    Map PADDOCK_* environment variables to a config dict.
    Only includes keys for env vars that are actually set.
    """
    config: dict = {}
    build: dict = {}

    _scalar_map = {
        'PADDOCK_AGENT': 'agent',
        'PADDOCK_IMAGE': 'image',
        'PADDOCK_NETWORK': 'network',
    }
    _build_map = {
        'PADDOCK_BUILD_CONTEXT': 'context',
        'PADDOCK_BUILD_DOCKERFILE': 'dockerfile',
        'PADDOCK_BUILD_POLICY': 'policy',
    }

    for env_key, config_key in _scalar_map.items():
        if env_key in environ:
            config[config_key] = environ[env_key]

    for env_key, build_key in _build_map.items():
        if env_key in environ:
            build[build_key] = environ[env_key]

    if build:
        config['build'] = build

    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/config/test_env.py -v
```

- [ ] **Step 5: Commit**

---

## Task 5: CLI Argument Parser

**Files:**
- Create: `src/paddock/cli.py`
- Create: `tests/test_cli.py`

Parses paddock flags, then treats the first positional arg (or first unknown flag, or everything after `--`) as the start of the container command. Returns a `ParsedArgs` dataclass.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
from paddock.cli import parse_args


def test_no_args():
    result = parse_args([])
    assert result.image is None
    assert result.agent is None
    assert result.command == []
    assert result.volumes == {}
    assert not result.dry_run
    assert not result.quiet


def test_image_flag():
    result = parse_args(['--image=ubuntu:22.04'])
    assert result.image == 'ubuntu:22.04'
    assert result.command == []


def test_agent_flag():
    result = parse_args(['--agent=claude'])
    assert result.agent == 'claude'


def test_positional_becomes_command():
    result = parse_args(['claude', '--agent=plan'])
    assert result.command == ['claude', '--agent=plan']
    assert result.agent is None


def test_paddock_flag_before_positional():
    result = parse_args(['--image=foo', 'claude', '--agent=plan'])
    assert result.image == 'foo'
    assert result.command == ['claude', '--agent=plan']


def test_double_dash_splits():
    result = parse_args(['--image=foo', '--', '--resume'])
    assert result.image == 'foo'
    assert result.command == ['--resume']


def test_unknown_flag_passes_through():
    result = parse_args(['--resume'])
    assert result.command == ['--resume']


def test_volume_flag():
    result = parse_args(['--volume=/host:/container:rw'])
    assert result.volumes == {'/host': '/container:rw'}


def test_volume_flag_repeated():
    result = parse_args(['--volume=/a:/ca', '--volume=/b:/cb:ro'])
    assert result.volumes == {'/a': '/ca', '/b': '/cb:ro'}


def test_volume_flag_no_mode():
    result = parse_args(['--volume=/host:/container'])
    assert result.volumes == {'/host': '/container'}


def test_dry_run_flag():
    result = parse_args(['--dry-run'])
    assert result.dry_run


def test_quiet_flag():
    result = parse_args(['--quiet'])
    assert result.quiet
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 3: Implement `src/paddock/cli.py`**

```python
import argparse
from dataclasses import dataclass, field


@dataclass
class ParsedArgs:
    agent: str | bool | None
    build_context: str | None
    build_dockerfile: str | None
    build_policy: str | None
    command: list[str]
    dry_run: bool
    image: str | None
    network: str | None
    quiet: bool
    volumes: dict[str, str]


def _parse_volume(value: str) -> tuple[str, str]:
    """Parse '--volume=/host:/container[:mode]' into (host_path, container_path_with_mode)."""
    parts = value.split(':', 1)
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(f'Invalid volume format: {value!r}. Expected /host:/container[:mode]')
    host, rest = parts
    return host, rest


def parse_args(argv: list[str]) -> ParsedArgs:
    """
    Parse paddock CLI arguments.

    Stops consuming paddock flags at the first positional arg or first unknown flag
    (treats them as the start of the container command). '--' explicitly splits
    paddock flags from the container command.
    """
    # Split on '--'
    if '--' in argv:
        split_idx = argv.index('--')
        before_dd = argv[:split_idx]
        after_dd = argv[split_idx + 1:]
    else:
        before_dd = argv
        after_dd = []

    parser = argparse.ArgumentParser(prog='paddock', add_help=True)
    parser.add_argument('--agent')
    parser.add_argument('--build-context')
    parser.add_argument('--build-dockerfile')
    parser.add_argument('--build-policy')
    parser.add_argument('--dry-run', action='store_true', default=False)
    parser.add_argument('--image')
    parser.add_argument('--network')
    parser.add_argument('--quiet', action='store_true', default=False)
    parser.add_argument('--volume', action='append', default=[])

    namespace, remaining = parser.parse_known_args(before_dd)

    # remaining contains either unknown flags or positional args (or both)
    # Everything in remaining + after_dd becomes the container command
    command = remaining + after_dd

    # Parse volumes: --volume=/host:/container[:mode]
    volumes: dict[str, str] = {}
    for vol in namespace.volume:
        host, rest = _parse_volume(vol)
        volumes[host] = rest

    return ParsedArgs(
        agent=namespace.agent,
        build_context=namespace.build_context,
        build_dockerfile=namespace.build_dockerfile,
        build_policy=namespace.build_policy,
        command=command,
        dry_run=namespace.dry_run,
        image=namespace.image,
        network=namespace.network,
        quiet=namespace.quiet,
        volumes=volumes,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 5: Commit**

---

## Task 6: Agent Base Class and Registry

**Files:**
- Create: `src/paddock/agents/__init__.py`
- Create: `src/paddock/agents/base.py`
- Create: `tests/agents/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_base.py  (minimal — mostly tests the registry lookup)
import pytest
from class_registry import RegistryKeyError
from paddock.agents import agent_registry
from paddock.agents.base import BaseAgent


def test_registry_contains_claude():
    assert 'claude' in agent_registry


def test_registry_contains_false():
    assert 'false' in agent_registry


def test_unknown_agent_raises():
    with pytest.raises(RegistryKeyError):
        agent_registry.get('unknown-agent')


def test_agent_has_required_methods():
    agent = agent_registry.get('claude')
    assert isinstance(agent, BaseAgent)
    assert hasattr(agent, 'get_command')
    assert hasattr(agent, 'get_volumes')
    assert hasattr(agent, 'get_scratch_volumes')
    assert hasattr(agent, 'get_build_args')
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/agents/test_base.py -v
```

- [ ] **Step 3: Implement `src/paddock/agents/base.py`**

```python
from abc import ABC, abstractmethod
from typing import ClassVar


class BaseAgent(ABC):
    AGENT_KEY: ClassVar[str]

    @abstractmethod
    def get_command(self) -> list[str]:
        """Default command to run in the container."""

    @abstractmethod
    def get_volumes(self) -> dict[str, str]:
        """
        Host-path-keyed volume mounts specific to this agent.
        Values are '/container/path' or '/container/path:mode'.
        """

    def get_scratch_volumes(self, image: str) -> dict[str, str]:
        """
        Named Docker volumes (not host paths) to create and mount.
        Keys are volume names, values are container paths.
        Override when the agent needs persistent storage that must not be
        shared with the host (e.g. SQLite WAL files).
        """
        return {}

    def get_build_args(self) -> dict[str, str]:
        """
        Docker build args to pass when building the paddock base image.
        Used when the built-in Dockerfile is referenced in the build config.
        """
        return {}
```

- [ ] **Step 4: Implement `src/paddock/agents/__init__.py`**

```python
from class_registry.entry_points import EntryPointClassRegistry

from paddock.agents.base import BaseAgent

agent_registry: EntryPointClassRegistry[BaseAgent] = EntryPointClassRegistry('paddock.agents')
```

- [ ] **Step 5: Run tests to verify they pass**

Note: the registry tests require the package to be installed in dev mode so entry points are discoverable. Run:
```bash
uv run pip install -e .
uv run pytest tests/agents/test_base.py -v
```

- [ ] **Step 6: Commit**

---

## Task 7: ShellAgent

**Files:**
- Create: `src/paddock/agents/shell.py`
- Create: `tests/agents/test_shell.py`

ShellAgent is used when `agent = false` in config. It drops the user into `/bin/bash`.

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_shell.py
from paddock.agents.shell import ShellAgent


def test_command():
    assert ShellAgent().get_command() == ['/bin/bash']


def test_volumes_empty():
    assert ShellAgent().get_volumes() == {}


def test_scratch_volumes_empty():
    assert ShellAgent().get_scratch_volumes('ubuntu:22.04') == {}


def test_build_args():
    assert ShellAgent().get_build_args() == {'AGENT': 'none'}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/agents/test_shell.py -v
```

- [ ] **Step 3: Implement `src/paddock/agents/shell.py`**

```python
from paddock.agents.base import BaseAgent


class ShellAgent(BaseAgent):
    AGENT_KEY = 'false'

    def get_command(self) -> list[str]:
        return ['/bin/bash']

    def get_volumes(self) -> dict[str, str]:
        return {}

    def get_build_args(self) -> dict[str, str]:
        return {'AGENT': 'none'}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/agents/test_shell.py -v
```

- [ ] **Step 5: Commit**

---

## Task 8: ClaudeAgent

**Files:**
- Create: `src/paddock/agents/claude.py`
- Create: `tests/agents/test_claude.py`

ClaudeAgent mounts `~/.claude` for auth/config persistence.

- [ ] **Step 1: Write failing tests**

```python
# tests/agents/test_claude.py
from pathlib import Path
from paddock.agents.claude import ClaudeAgent


def test_command():
    assert ClaudeAgent().get_command() == ['claude']


def test_volumes_mount_claude_dir():
    volumes = ClaudeAgent().get_volumes()
    expected_host = str(Path.home() / '.claude')
    assert expected_host in volumes
    assert volumes[expected_host] == '/root/.claude:rw'


def test_scratch_volumes_empty():
    # Claude doesn't need a scratch volume
    assert ClaudeAgent().get_scratch_volumes('ubuntu:22.04') == {}


def test_build_args():
    assert ClaudeAgent().get_build_args() == {'AGENT': 'claude'}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/agents/test_claude.py -v
```

- [ ] **Step 3: Implement `src/paddock/agents/claude.py`**

```python
from pathlib import Path

from paddock.agents.base import BaseAgent


class ClaudeAgent(BaseAgent):
    AGENT_KEY = 'claude'

    def get_command(self) -> list[str]:
        return ['claude']

    def get_volumes(self) -> dict[str, str]:
        return {str(Path.home() / '.claude'): '/root/.claude:rw'}

    def get_build_args(self) -> dict[str, str]:
        return {'AGENT': 'claude'}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/agents/test_claude.py -v
```

- [ ] **Step 5: Commit**

---

## Task 9: Docker Command Builder

**Files:**
- Create: `src/paddock/docker/__init__.py`
- Create: `src/paddock/docker/builder.py`
- Create: `tests/docker/test_builder.py`

Assembles the full `docker run` argv list from the validated config, the resolved agent, and the CWD.

Scratch volume naming: `paddock_{sanitized_image}_{agent_key}` where sanitize replaces all non-`[a-z0-9]` characters with `_`.

- [ ] **Step 1: Write failing tests**

```python
# tests/docker/test_builder.py
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from paddock.docker.builder import build_docker_argv, sanitise_volume_name


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


def test_minimal_command(tmp_path):
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent()
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=[])
    assert argv[0] == 'docker'
    assert 'run' in argv
    assert '--rm' in argv
    assert '-it' in argv
    assert f'--workdir=/workspace' in argv
    assert f'{tmp_path}:/workspace:rw' in ' '.join(argv)
    assert 'ubuntu:22.04' in argv


def test_uses_agent_command(tmp_path):
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(command=['claude'])
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=[])
    assert argv[-1] == 'claude'


def test_command_override(tmp_path):
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(command=['claude'])
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=['opencode', '--flag'])
    assert argv[-2:] == ['opencode', '--flag']


def test_config_volumes(tmp_path):
    config = {
        'image': 'ubuntu:22.04',
        'agent': 'claude',
        'volumes': {'/host/data': '/data:ro'},
        'network': None,
    }
    agent = make_agent()
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=[])
    assert '-v' in argv
    idx = argv.index('-v')
    # find the /host/data volume
    volume_args = [argv[i+1] for i, a in enumerate(argv) if a == '-v']
    assert any('/host/data:/data:ro' in v for v in volume_args)


def test_network(tmp_path):
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': 'mynet'}
    agent = make_agent()
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=[])
    assert '--network' in argv
    assert 'mynet' in argv


def test_scratch_volume(tmp_path):
    config = {'image': 'ubuntu:22.04', 'agent': 'claude', 'volumes': {}, 'network': None}
    agent = make_agent(scratch_volumes={'paddock_ubuntu_22_04_claude': '/scratch'})
    argv = build_docker_argv(config=config, agent=agent, cwd=tmp_path, command=[])
    volume_args = [argv[i+1] for i, a in enumerate(argv) if a == '-v']
    assert any('paddock_ubuntu_22_04_claude:/scratch' in v for v in volume_args)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/docker/test_builder.py -v
```

- [ ] **Step 3: Implement `src/paddock/docker/builder.py`**

```python
import re
from pathlib import Path

from paddock.agents.base import BaseAgent


def sanitise_volume_name(image: str, agent_key: str) -> str:
    """Generate a Docker volume name from image + agent key."""
    sanitised = re.sub(r'[^a-z0-9]', '_', image.lower())
    return f'paddock_{sanitised}_{agent_key}'


def _volume_flag(host_or_name: str, container_spec: str) -> list[str]:
    return ['-v', f'{host_or_name}:{container_spec}']


def build_docker_argv(
    *,
    config: dict,
    agent: BaseAgent,
    cwd: Path,
    command: list[str],
) -> list[str]:
    """Assemble the full 'docker run' argv list."""
    argv = ['docker', 'run', '--rm', '-it', '--workdir=/workspace']

    # CWD as workspace
    argv += _volume_flag(str(cwd), '/workspace:rw')

    # Agent-specific volumes
    for host, container in agent.get_volumes().items():
        argv += _volume_flag(host, container)

    # Config volumes
    for host, container in config.get('volumes', {}).items():
        container_spec = container if ':' in container else f'{container}:ro'
        argv += _volume_flag(host, container_spec)

    # Scratch volumes (named Docker volumes)
    for vol_name, container_path in agent.get_scratch_volumes(config['image']).items():
        argv += _volume_flag(vol_name, container_path)

    # Network
    if config.get('network'):
        argv += ['--network', config['network']]

    # Image
    argv.append(config['image'])

    # Command: CLI override takes precedence over agent default
    argv += command if command else agent.get_command()

    return argv
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/docker/test_builder.py -v
```

- [ ] **Step 5: Commit**

---

## Task 10: Image Auto-Build

**Files:**
- Create: `src/paddock/docker/build.py`
- Create: `tests/docker/test_build.py`

Implements build policies: `if-missing`, `always`, `daily`, `weekly`. Calls `docker build` when the policy requires it.

- [ ] **Step 1: Write failing tests**

```python
# tests/docker/test_build.py
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, call
import pytest
from paddock.docker.build import should_build, run_build, BuildPolicy


def test_should_build_always():
    assert should_build(BuildPolicy.ALWAYS, image_created_at=datetime.now(timezone.utc))


def test_should_build_if_missing_image_exists():
    assert not should_build(BuildPolicy.IF_MISSING, image_created_at=datetime.now(timezone.utc))


def test_should_build_if_missing_image_absent():
    assert should_build(BuildPolicy.IF_MISSING, image_created_at=None)


def test_should_build_daily_old_image():
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    assert should_build(BuildPolicy.DAILY, image_created_at=old)


def test_should_build_daily_fresh_image():
    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    assert not should_build(BuildPolicy.DAILY, image_created_at=fresh)


def test_should_build_weekly_old_image():
    old = datetime.now(timezone.utc) - timedelta(days=8)
    assert should_build(BuildPolicy.WEEKLY, image_created_at=old)


def test_run_build_basic(mocker):
    mock_run = mocker.patch('paddock.docker.build.subprocess.run')
    run_build(
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
    run_build(
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


class BuildPolicy(StrEnum):
    ALWAYS = 'always'
    DAILY = 'daily'
    IF_MISSING = 'if-missing'
    WEEKLY = 'weekly'


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


def get_image_created_at(image: str) -> datetime | None:
    """Return the creation timestamp of a local Docker image, or None if absent."""
    result = subprocess.run(
        ['docker', 'image', 'inspect', '--format={{.Created}}', image],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    created_str = result.stdout.strip()
    return datetime.fromisoformat(created_str.rstrip('Z')).replace(tzinfo=timezone.utc)


def run_build(*, image: str, dockerfile: str, context: str, build_args: dict[str, str]) -> None:
    """Run docker build."""
    argv = ['docker', 'build', '-t', image, '-f', dockerfile]
    for key, value in build_args.items():
        argv += ['--build-arg', f'{key}={value}']
    argv.append(context)
    subprocess.run(argv, check=True)


def maybe_build(*, build_config: dict, image: str, build_args: dict[str, str]) -> None:
    """Build the image if the build policy requires it."""
    policy = BuildPolicy(build_config.get('policy', 'if-missing'))
    dockerfile = build_config['dockerfile']
    context = build_config.get('context') or str(Path(dockerfile).parent)

    image_created_at = get_image_created_at(image)
    if should_build(policy, image_created_at):
        run_build(image=image, dockerfile=dockerfile, context=context, build_args=build_args)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/docker/test_build.py -v
```

- [ ] **Step 5: Commit**

---

## Task 11: Main Entry Point

**Files:**
- Modify: `src/paddock/__main__.py`
- Create: `tests/test_main.py`

Orchestrates the full flow: parse CLI → load + merge config → validate → log → maybe build → run docker.

Logging: INFO level by default (suppressed with `--quiet`). Logs each resolved config value. Prints the full docker command before running.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from paddock.__main__ import run


@pytest.fixture
def minimal_config(tmp_path):
    config_dir = tmp_path / '.paddock'
    config_dir.mkdir()
    cfg = config_dir / 'config.toml'
    cfg.write_text('image = "ubuntu:22.04"\nagent = "claude"\n')
    return tmp_path


def test_dry_run_exits_zero(minimal_config, capsys, monkeypatch):
    monkeypatch.chdir(minimal_config)
    with patch('paddock.__main__.subprocess') as mock_sub:
        with pytest.raises(SystemExit) as exc:
            run(['--dry-run'])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert 'docker' in captured.out


def test_quiet_suppresses_logs(minimal_config, capsys, monkeypatch):
    monkeypatch.chdir(minimal_config)
    with patch('paddock.__main__.subprocess') as mock_sub:
        run(['--quiet'])
    captured = capsys.readouterr()
    assert 'Using image' not in captured.out


def test_missing_image_exits_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run([])
    assert exc.value.code == 1


def test_runs_docker(minimal_config, monkeypatch):
    monkeypatch.chdir(minimal_config)
    with patch('paddock.__main__.subprocess.run') as mock_run:
        run([])
    mock_run.assert_called_once()
    docker_argv = mock_run.call_args[0][0]
    assert docker_argv[0] == 'docker'
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
from paddock.agents.base import BaseAgent
from paddock.cli import parse_args
from paddock.config.env import env_to_config
from paddock.config.loader import apply_defaults, load_config_files, merge_configs
from paddock.config.schema import validate_config
from paddock.docker.build import maybe_build
from paddock.docker.builder import build_docker_argv

_USER_CONFIG = Path.home() / '.config' / 'paddock' / 'config.toml'
_PROJECT_CONFIG_NAME = Path('.paddock') / 'config.toml'

logger = logging.getLogger('paddock')


def _setup_logging(quiet: bool) -> None:
    if quiet:
        logging.disable(logging.CRITICAL)
    else:
        logging.basicConfig(level=logging.INFO, format='%(message)s')


def _cli_args_to_config(parsed) -> dict:
    """Map ParsedArgs fields to a config-shaped dict (omitting None values)."""
    config: dict = {}
    build: dict = {}

    if parsed.image is not None:
        config['image'] = parsed.image
    if parsed.agent is not None:
        config['agent'] = parsed.agent
    if parsed.network is not None:
        config['network'] = parsed.network
    if parsed.build_dockerfile is not None:
        build['dockerfile'] = parsed.build_dockerfile
    if parsed.build_context is not None:
        build['context'] = parsed.build_context
    if parsed.build_policy is not None:
        build['policy'] = parsed.build_policy
    if build:
        config['build'] = build
    if parsed.volumes:
        config['volumes'] = parsed.volumes

    return config


def run(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    _setup_logging(parsed.quiet)

    cwd = Path.cwd()

    # Load and merge config from all sources
    file_config = load_config_files(
        user_config=_USER_CONFIG,
        project_config=cwd / _PROJECT_CONFIG_NAME,
    )
    env_config = env_to_config(dict(os.environ))
    cli_config = _cli_args_to_config(parsed)

    merged = merge_configs(file_config, env_config)
    merged = merge_configs(merged, cli_config)
    # CLI volumes are additive; already merged above via merge_configs
    apply_defaults(merged)
    config = validate_config(merged)

    # Resolve agent
    agent_key = 'false' if config['agent'] is False else str(config['agent'])
    agent: BaseAgent = agent_registry.get(agent_key)

    # Log resolved configuration
    logger.info('Using image: %s', config['image'])
    logger.info('Agent: %s', config['agent'])
    for host, container in config['volumes'].items():
        logger.info('Mounting %s → %s', host, container)
    if config.get('network'):
        logger.info('Network: %s', config['network'])

    # Maybe build image
    if config.get('build'):
        maybe_build(
            build_config=config['build'],
            image=config['image'],
            build_args=agent.get_build_args(),
        )

    # Assemble and run docker command
    docker_argv = build_docker_argv(
        config=config,
        agent=agent,
        cwd=cwd,
        command=parsed.command,
    )

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

---

## Task 12: Base Dockerfile

**Files:**
- Create: `images/Dockerfile`

Ubuntu base image with Python via deadsnakes. Accepts `ARG AGENT` to pre-install the appropriate coding agent.

- [ ] **Step 1: Create `images/Dockerfile`**

```dockerfile
FROM ubuntu:24.04

ARG AGENT=none
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
    python${PYTHON_VERSION} \
    python${PYTHON_VERSION}-venv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Claude Code)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install coding agent based on ARG
RUN case "$AGENT" in \
    claude) npm install -g @anthropic-ai/claude-code ;; \
    none) echo "No agent selected" ;; \
    *) echo "Unknown agent: $AGENT" && exit 1 ;; \
    esac

WORKDIR /workspace
```

- [ ] **Step 2: Verify Dockerfile builds (manual check)**

```bash
docker build -t paddock-test --build-arg AGENT=none images/
docker build -t paddock-claude --build-arg AGENT=claude images/
```

- [ ] **Step 3: Commit**

---

## Verification

Run the full test suite:

```bash
uv run pytest -v --tb=short
```

Smoke test the CLI end-to-end (requires Docker):

```bash
# From any directory with an image available
uv run paddock --image=ubuntu:22.04 --agent=false --dry-run
# Expected: prints 'docker run --rm -it ...' and exits 0

uv run paddock --image=ubuntu:22.04 --agent=false --quiet
# Expected: drops into /bin/bash in container, no log output
```

---

## Phase 2 (Future)

Squid proxy sidecar: a second container started alongside the paddock container that routes all outbound internet traffic through a configurable proxy. The paddock container reaches the internet only via the proxy. Web UI for monitoring traffic. Policy file support. Paddock must not be able to reach the sidecar's admin interfaces.
