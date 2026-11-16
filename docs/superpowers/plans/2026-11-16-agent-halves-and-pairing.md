# Agent Halves and Pairing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Config can choose a client and a server separately, Paddock resolves and
checks the pair, and server settings have a validated home, all before any server
container exists.

**Architecture:** This is the first half of the second pull request in the design;
the second half adds the managed server container and OpenCode. Here `agent` becomes
a table of two halves that sources merge half by half, `BaseAgent` gains the
attributes that make it the client half, a `BaseServer` registry is added, and an
`AgentPairing` class checks the pair. No bundled server exists yet, so a run that
chooses a server stops. Completed pre-work: ADRs 018 and 019 are committed on the
branch (`31ea861`) and are the binding record; this plan file is committed too.

**Tech Stack:** Python, phx-filters, phx-class-registry, pytest.

**Spec:** `docs/adr/018-split-agents-into-clients-and-servers.md` (all of it) and
`docs/adr/019-run-one-shared-container-per-agent-server.md` (its Settings bullet
only). The wider design is
`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`.

**Worktree:** `/home/user/paddock` (branch: `claude/laughing-knuth-e8mouz`). A cloud
session's container is already isolated and may push only to this branch, so no
separate worktree exists.

## Global Constraints

- Each half of `agent` is unnamed, named, or `false` (the shell for the client, none
  for the server). A string or `false` names the client and resets the server to
  unnamed. A table names only the halves it lists; its keys are `client` and
  `server` and nothing else.
- Sources merge half by half. After the merge an unnamed client is `claude` and an
  unnamed server is the merged client's `DEFAULT_SERVER`.
- Within one source the whole value applies first, reset included, then that
  source's halves.
- `agent` stays one allowlist directive.
- A client is paired with a server when both name the same non-`None` `PROTOCOL`. A
  client with a `PROTOCOL` must be paired or the run stops. A client without one may
  be chosen beside any server.
- A chosen client or server that is not installed stops the run after the merge,
  before `.paddock` is created.
- `agents.<name>.server` (keys `build`, `image`, `port`, `volumes`) is valid only in
  the user config's global section. In a `[projects]` entry it is a validation
  error. In the project file it is discarded before validation, whatever the
  allowlist grants, with a warning of its own when that file is enabled; a disabled
  project file is ignored whole and draws none. Its host paths must be absolute after `~`
  expansion; nothing is looked up on disk in this plan.
- `extra_args` needs a client named `<name>`; `server` needs a server named
  `<name>`; either without one draws a warning and is ignored (ADR 017). An empty
  list of installed servers reads `none` in every message.
- Strings go through `f.Unicode`; `f.Type(str)` goes in front where a non-string
  must be an error (the `phx-filters` skill).
- Registries are injected, never patched: anything that consults `agent_registry`
  or `server_registry` takes them as keyword arguments defaulting to the real ones,
  so tests pass a `class_registry.ClassRegistry` of fakes.
- Commit with `uv run git commit`, from the repo root. NZ English. Flat test
  functions, no lambdas in `parametrize`, Google-style docstrings, comments on the
  line above, implementation in classes.
- The suite collects 364 tests before this plan; the count must rise.

## Review Focus

1. A client-only override (`--agent-client=x` over a user-level `agent = "claude"`):
   the server follows the new client's default, not the old one's. Task 2.
2. A string above a table (`[projects]` entry `agent = "claude"` over user-level
   `agent = { server = "srv" }`): the server is reset, not kept. Task 2.
3. `PADDOCK_AGENT` with `PADDOCK_AGENT_SERVER`: both are honoured; today's
   name-to-path mapping would lose the first. Task 2
   (`test_env.py::test_agent_whole_then_half`).
4. A typo inside the table (`agent = { clinet = "x" }`): an error at `agent.clinet`,
   not a silent default. Task 2.
5. A project file holding `[agents.x.server]`, even a malformed one: the run goes
   ahead with a warning that names it. Task 3.
6. `agent.server` naming a server that is not installed: exit 1 listing the
   installed servers, with `.paddock` never created. Task 4.

## File Map

- `src/paddock/agents/`: `BaseAgent` attributes; new `servers.py` (`BaseServer`,
  `ServerConnection`, `server_registry`); new `pairing.py` (`AgentPairing`).
- `src/paddock/config/`: `agent_choice.py` (new), `filters.py`, `schema.py`,
  `loader.py`, `sources/` (`base.py`, `cli.py`, `env.py`, `project_toml.py`,
  `user.py`).
- `src/paddock/cli.py`, `src/paddock/__main__.py`.
- `tests/` mirrors each.

---

### Task 1: Client attributes and the server registry

**Files:**
- Modify: `src/paddock/agents/__init__.py`
- Create: `src/paddock/agents/servers.py`
- Test: `tests/agents/test_base.py` (create if absent), `tests/agents/test_servers.py`

**Interfaces:**
- Produces, on `BaseAgent`:
  `DEFAULT_SERVER: ClassVar[str | None] = None`,
  `PROTOCOL: ClassVar[str | None] = None`,
  `get_server_args(self, connection: ServerConnection) -> list[str]` returning `[]`,
  `get_server_env(self, connection: ServerConnection) -> dict[str, str]` returning
  `{}`.
- Produces, in `paddock.agents.servers`:
  - `@dataclass(frozen=True) class ServerConnection` with fields
    `container_url: str`, `host_url: str`, `network: str`, `secret: str`.
  - `class BaseServer(ABC)` with `SERVER_KEY: ClassVar[str]`,
    `PROTOCOL: ClassVar[str]`, `CONTAINER_PORT: ClassVar[int]`,
    `DEFAULT_IMAGE: ClassVar[str | None] = None`,
    `REQUIRES_WORKDIR_MOUNT: ClassVar[bool] = False`; abstract
    `get_command(self) -> list[str]` and
    `is_ready(self, connection: ServerConnection) -> bool`; concrete defaults
    `get_volumes(self) -> dict[str, VolumeSpec]` (`{}`),
    `get_scratch_volumes(self) -> dict[str, VolumeSpec]` (`{}`),
    `get_build_args(self) -> dict[str, str]` (`{}`),
    `get_env(self, secret: str) -> dict[str, str]` (`{}`).
  - `server_registry: EntryPointClassRegistry = EntryPointClassRegistry("paddock.servers")`.
  - `installed_server_keys() -> list[str]`, sorted, beside the registry, as
    `installed_agent_keys()` is.
- `ServerConnection` lives in `servers.py`, and `agents/__init__.py` imports it
  directly. `servers.py` must import nothing from `paddock.agents`, only
  `VolumeSpec` from `paddock.config.filters`, so there is no cycle.

- [ ] **Step 1: Write the failing tests.** The first goes in `test_base.py`, the
  other four in `test_servers.py`.

  - `test_agent_defaults_preserve_todays_behaviour`: `ClaudeAgent` and `ShellAgent`
    have `DEFAULT_SERVER is None` and `PROTOCOL is None`; with any
    `ServerConnection`, `get_server_args` returns `[]` and `get_server_env` `{}`.
  - `test_server_registry_is_empty_without_plugins`:
    `installed_server_keys() == []`.
  - `test_base_server_defaults`: a minimal concrete subclass defined in the test
    returns `{}` from `get_volumes`, `get_scratch_volumes`, `get_build_args` and
    `get_env("s")`, has `DEFAULT_IMAGE is None` and
    `REQUIRES_WORKDIR_MOUNT is False`.
  - `test_base_server_is_abstract`: instantiating `BaseServer` raises `TypeError`.
  - `test_server_connection_is_immutable`: assigning a field raises
    `dataclasses.FrozenInstanceError`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/agents -q --continue-on-collection-errors`
  Expected: both test files error at collection, each importing a name this task
  adds; nothing in them runs yet.

- [ ] **Step 3: Implement** the interfaces above. Each method and class gets a
  docstring; `BaseServer`'s class docstring cites ADR 018.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 2: `agent` as two halves

**Files:**
- Create: `src/paddock/config/agent_choice.py`
- Modify: `src/paddock/config/filters.py`, `src/paddock/config/loader.py`,
  `src/paddock/config/sources/cli.py`, `src/paddock/config/sources/env.py`,
  `src/paddock/cli.py`, `src/paddock/__main__.py`
- Test: `tests/config/test_agent_choice.py`, `tests/config/test_filters.py`,
  `tests/config/test_loader.py`, `tests/config/test_schema.py`,
  `tests/config/test_context.py`, every file under `tests/config/sources/`,
  `tests/test_cli.py`, `tests/test_main.py`
- Eight test helpers build `ParsedArgs` with every field (`tests/config/`
  `test_loader.py`, `test_context.py`, and `sources/test_base.py`, `test_cli.py`,
  `test_env.py`, `test_project_overrides.py`, `test_project_toml.py`,
  `test_user.py`); each gains `agent_client=None, agent_server=None`.
- Existing tests that assert the scalar `agent` and must assert the full table
  instead: `test_filters.py::test_agent_string`, `test_agent_false_string`,
  `test_agent_false_bool`, `test_agent_table_rejected`;
  `test_loader.py::test_apply_defaults`; `test_schema.py::test_valid_minimal`,
  `test_agent_false`; `sources/test_user.py::test_load_strips_projects_and_config`;
  `sources/test_project_toml.py::test_load_returns_validated_config`.

**Interfaces:**
- Consumes: `BaseAgent.DEFAULT_SERVER` from Task 1.
- Produces, in `paddock.config.agent_choice`:
  - `UNNAMED_SERVER = "<default>"`: the stored value of a server half that was
    reset. It is an ordinary string so it survives `DropEmpty` and a second pass
    through the schema.
  - `class AgentChoice` with
    `@staticmethod from_parts(whole: str | bool | None, *, client: str | bool | None = None, server: str | bool | None = None) -> dict | None`.
    `whole` given: start from `{"client": whole, "server": UNNAMED_SERVER}`. Then
    overlay each of `client` and `server` that is not `None`. Nothing given: `None`.
    It does not validate.
- Produces: the `Agent` filter's cleaned value is always a table holding any of
  `client: str | False` and `server: str | False`. Input forms: a string or `False`
  (via `AgentChoice.from_parts`), or a table whose keys are `client` and `server`.
  In either half the string `"false"` maps to `False`. It is idempotent on its own
  output.
- Produces, on `ResolvedConfig`: `agent_key: str` (unchanged meaning) and
  `server_key: str | None`. `resolved.config["agent"]` is
  `{"client": str | False, "server": str | False}`, both halves resolved.
- Produces, on `ConfigLoader.__init__`: keyword `agents` defaulting to
  `agent_registry`, used wherever the loader consults the registry.
- Produces, on `ParsedArgs`: `agent_client: str | bool | None` and
  `agent_server: str | bool | None`, from `--agent-client` and `--agent-server`.

- [ ] **Step 1: Write the failing tests**

  `tests/config/test_agent_choice.py`:
  - `test_whole_resets_the_server`: `from_parts("claude")` is
    `{"client": "claude", "server": UNNAMED_SERVER}`.
  - `test_false_is_the_shell_and_resets_the_server`: `from_parts(False)` is
    `{"client": False, "server": UNNAMED_SERVER}`.
  - `test_halves_apply_after_the_whole`:
    `from_parts("claude", server="srv")` is `{"client": "claude", "server": "srv"}`;
    `from_parts("claude", client="other")` is
    `{"client": "other", "server": UNNAMED_SERVER}`.
  - `test_a_half_alone_names_only_itself`: `from_parts(None, server="srv")` is
    `{"server": "srv"}`; `from_parts(None, server=False)` is `{"server": False}`.
  - `test_nothing_given_is_none`: `from_parts(None)` is `None`.

  `tests/config/test_filters.py`, rewriting the four existing `Agent` tests named
  above and adding:
  - `test_agent_string`: `"claude"` cleans to
    `{"client": "claude", "server": UNNAMED_SERVER}`.
  - `test_agent_false_bool` and `test_agent_false_string`: `False` and `"false"`
    clean to `{"client": False, "server": UNNAMED_SERVER}`.
  - `test_agent_table_names_only_its_halves`: `{"client": "x"}` cleans to itself;
    `{"server": "false"}` to `{"server": False}`; `{"client": "false"}` to
    `{"client": False}`.
  - `test_agent_is_idempotent`: applying `Agent` to each cleaned value above returns
    it unchanged.
  - `test_agent_rejects_an_unknown_half`: `{"clinet": "x"}` gives
    `{"clinet": [f.FilterMapper.CODE_EXTRA_KEY]}`.
  - `test_agent_table_rejected`, kept for `[agent.claude]` written for
    `[agents.claude]`: `{"claude": {}}` gives
    `{"claude": [f.FilterMapper.CODE_EXTRA_KEY]}`.
  - `test_agent_rejects_a_non_string_half`: `{"client": 1}` gives
    `{"client": [f.Type.CODE_WRONG_TYPE]}`; `{"client": ""}` gives
    `{"client": [f.NotEmpty.CODE_EMPTY]}`; `{"server": True}` gives
    `{"server": [AgentHalf.CODE_INVALID]}`.
  - `test_agent_rejects_a_list`: `["claude"]` gives `[f.Type.CODE_WRONG_TYPE]`.
  - `test_agent_true_rejected`: tighten it to assert `[Agent.CODE_INVALID]`, the
    code `True` gives today and keeps.
  - `test_agent_rejects_an_empty_table` in `tests/config/test_schema.py`:
    `{"agent": {}}` under `merged=True` gives `{"agent": [f.NotEmpty.CODE_EMPTY]}`.
  - `test_agent_half_pass_none`: `AgentHalf` passes `None` through, as the
    `phx-filters` skill requires of every custom filter's first test.

  `tests/config/test_loader.py`. Define two fakes at module level, a client
  `FakePaired` (`AGENT_KEY = "paired"`, `DEFAULT_SERVER = "srv"`) and a plain
  `FakePlain` (`AGENT_KEY = "plain"`), in a `ClassRegistry(attr_name="AGENT_KEY")`
  also holding `claude` and `false` stand-ins, passed as `ConfigLoader(agents=...)`:
  - `test_string_takes_the_clients_default_server`: `agent = "paired"` resolves to
    `agent_key == "paired"`, `server_key == "srv"`,
    `config["agent"] == {"client": "paired", "server": "srv"}`.
  - `test_client_without_a_default_has_no_server`: `agent = "plain"` gives
    `server_key is None` and `config["agent"]["server"] is False`.
  - `test_no_agent_defaults_to_claude`: no `agent` anywhere gives
    `agent_key == "claude"`, `server_key is None`.
  - `test_table_overrides_only_the_server`: user `agent = "plain"`, `[projects]`
    entry `agent = { server = "srv" }` gives client `plain`, server `srv`.
  - `test_client_override_brings_its_default_server`: user `agent = "plain"`,
    `[projects]` entry `agent = { client = "paired" }` gives server `srv`.
  - `test_string_above_a_table_resets_the_server`: user
    `agent = { server = "srv" }`, `[projects]` entry `agent = "plain"` gives
    `server_key is None`.
  - `test_false_server_survives_a_default`: `agent = { client = "paired", server =
    false }` gives `server_key is None`.
  - `test_shell_resets_the_server`: user `agent = { server = "srv" }`, `[projects]`
    entry `agent = false` gives `agent_key == "false"`, `server_key is None`.
  - `test_unknown_client_resolves_without_a_server`: `agent = "nope"` resolves with
    `agent_key == "nope"`, `server_key is None`, and raises nothing (the entry point
    reports it, Task 4).
  - `test_agent_typo_in_table_is_a_config_error`: `agent = { clinet = "x" }` raises
    the `ExceptionGroup` with `[user:agent.clinet]` in a message.
  - `test_project_toml_agent_dropped_whole_unless_allowlisted`: with
    `project_toml = ["volumes"]` and a project file `agent = { server = "srv" }`,
    the warning names `agent` and `server_key is None`.
  - `test_project_toml_agent_table_kept_when_allowlisted`: with
    `project_toml = ["agent"]` and the same project file, `server_key == "srv"`:
    a source granted `agent` can name a server.
  Update the existing loader tests that read `config["agent"]` to the table form.

  `tests/test_cli.py`:
  - `test_agent_half_flags_populate_parsed_args`: `--agent-client=x` and
    `--agent-server=y` populate `ParsedArgs.agent_client` and `agent_server`; both
    default to `None`.
  - `test_agent_half_flags_accept_the_space_form`:
    `["--agent-client", "x", "--agent-server", "y"]` gives the same, with an empty
    `command`.
  - `test_agent_server_false_is_kept_as_written`: `--agent-server=false` is the
    string `"false"`, for the source to map.

  `tests/config/sources/test_cli.py` and `test_env.py`, the same three in each,
  from flags in one and variables in the other:
  - `test_agent_whole_then_half`: `--agent=claude --agent-server=srv` /
    `PADDOCK_AGENT=claude PADDOCK_AGENT_SERVER=srv` clean to
    `agent == {"client": "claude", "server": "srv"}`.
  - `test_agent_half_alone`: `--agent-client=x` / `PADDOCK_AGENT_CLIENT=x` clean
    to `agent == {"client": "x"}`.
  - `test_agent_server_false`: `--agent-server=false` /
    `PADDOCK_AGENT_SERVER=false` clean to `agent == {"server": False}`.

  `tests/test_main.py`: update assertions on the `Agent:` log line if any, and add
  `test_cli_client_override_runs_that_client`: user `agent = "claude"`,
  `run(["--dry-run", "--agent-client=false"])` prints an argv ending `/bin/bash`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/config tests/test_cli.py tests/test_main.py -q --continue-on-collection-errors`
  Expected: every test file that imports a name this task adds
  (`test_agent_choice.py`, `test_filters.py`, and any other importing
  `UNNAMED_SERVER` or `AgentHalf`) errors at collection; the rest of the new and
  rewritten tests FAIL. Tests built on the `ParsedArgs` helpers fail too until
  Step 3 adds the fields.

- [ ] **Step 3: Implement**

  - `agent_choice.py` as specified.
  - `Agent` filter: a table goes through
    `f.FilterMapper({"client": <half>, "server": <half>}, allow_extra_keys=False,
    allow_missing_keys=True)` with `None` values removed; a string or `False` goes
    through `AgentChoice.from_parts` first; `True` stays `Agent.CODE_INVALID`;
    anything else is `f.Type((bool, dict, str))`'s error. Update the
    `CODE_INVALID` template and the class docstring, which describe a name or
    `False` only. A
    half is `False`, or `"false"` mapped to `False`, or
    `f.Type(str) | f.Unicode | f.NotEmpty`; `True` is `CODE_INVALID`. Extract the
    half as its own filter class, `AgentHalf`, since the environment schema needs
    it too.
  - `cli.py`: `--agent-client` and `--agent-server`, plain strings like `--agent`,
    each also added to `_KNOWN_VALUE_FLAGS` so the space-separated form is not read
    as a replacement command.
  - `CliConfigSource`: `raw["agent"] = AgentChoice.from_parts(parsed.agent,
    client=parsed.agent_client, server=parsed.agent_server)` when not `None`.
  - `EnvConfigSource`: all three agent variables (`PADDOCK_AGENT`,
    `PADDOCK_AGENT_CLIENT`, `PADDOCK_AGENT_SERVER`) are `AgentHalf` in
    `_env_schema`, not `Agent`, whose table output `from_parts` would nest; `load` takes the three agent variables out of the
    cleaned mapping, builds the table with `AgentChoice.from_parts`, and sets
    `shaped["agent"]` directly, so `_deep_set` never sees them.
  - `ConfigLoader._apply_defaults`: default the halves, not the value:
    `agent.setdefault("client", "claude")` and
    `agent.setdefault("server", UNNAMED_SERVER)` on a table created if absent.
  - `ConfigLoader.resolve`: after the final validation, replace an
    `UNNAMED_SERVER` server with the client class's `DEFAULT_SERVER` or `False`,
    using `self._agents.get_class(agent_key)` only when `agent_key in self._agents`,
    else `False`. Set `server_key` to the server string or `None`. `_agent_key`
    now takes `config["agent"]["client"]`.
  - `__main__.py`: log `Agent: <agent_key>`. No `Server:` line yet: every run with
    a server stops before logging until the second half.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 3: Server settings in the `agents` table

**Files:**
- Modify: `src/paddock/config/schema.py`, `src/paddock/config/filters.py`,
  `src/paddock/config/loader.py`, `src/paddock/config/sources/base.py`,
  `src/paddock/config/sources/project_toml.py`,
  `src/paddock/config/sources/user.py`
- Test: `tests/config/test_schema.py`, `tests/config/test_filters.py`,
  `tests/config/test_loader.py`, `tests/config/sources/test_project_toml.py`

**Interfaces:**
- Consumes: `server_registry`, `installed_server_keys` from Task 1.
- Produces: `standard_config_schema(..., server_settings: bool = False)`. `True`
  adds a `server` key to each `agents.<name>` table; `merged=True` implies it.
  `user_config_schema` allows it in the global section only; `UserConfigSource`'s
  second pass passes `server_settings=True`.
- Produces: the merged config may hold
  `config["agents"][name]["server"]` with any of `image: str`,
  `port: int`, `build: dict` (as top-level `build`, host paths kept as written) and
  `volumes: dict[str, VolumeSpec]` keyed by the host path as written.
- Produces, on `LoadResult`: `discarded: list[str]` (default empty): dotted paths
  the source itself removed before validation.
- Produces, on `ConfigLoader.__init__`: keyword `servers` defaulting to
  `server_registry`.

- [ ] **Step 1: Write the failing tests**

  `tests/config/test_schema.py`, with `server_settings=True` unless stated:
  - `test_server_settings_accept_every_key`:
    `{"agents": {"x": {"server": {"image": "img", "port": 4096, "volumes":
    {"/abs": "/abs:rw"}, "build": {"dockerfile": "/abs/Dockerfile", "policy":
    "daily"}}}}}` is valid; `volumes` cleans to
    `{"/abs": VolumeSpec("/abs", "rw")}`.
  - `test_server_settings_reject_a_relative_volume`: `{"rel/dir": "/c:rw"}` is
    invalid at `agents.x.server.volumes.rel/dir`.
  - `test_server_settings_accept_a_tilde_volume`: `{"~/Dev": "~/Dev:rw"}` is valid;
    `{"~bob/Dev": "/c:rw"}` is not, `~` meaning home only as a whole first segment,
    the rule `Filepath` applies.

  - `test_server_settings_reject_a_relative_build_path`: `dockerfile = "Dockerfile"`
    is invalid at `agents.x.server.build.dockerfile`; likewise `context`.
  - `test_server_settings_reject_a_bad_port`: `0`, `65536`, `"4096"` and `True` are
    each invalid at `agents.x.server.port`.
  - `test_server_settings_reject_an_unknown_key`: `{"server": {"imge": "i"}}` gives
    `{"agents.x.server.imge": [f.FilterMapper.CODE_EXTRA_KEY]}`.
  - `test_server_settings_do_not_touch_disk`: a volume key and build paths that do
    not exist are valid.
  - Write no new test for the default: the existing
    `test_agents_rejects_an_unknown_setting` already pins that a `server` key is
    `CODE_EXTRA_KEY` without `server_settings`. Reword its docstring, "Only
    extra_args is a setting" no longer being true of every schema.
  - `test_projects_entry_rejects_server_settings`: a user config TOML with
    `[projects."/x".agents.y.server]` and `image = "i"` fails `user_config_schema`
    at a key ending `agents.y.server`.
  - `test_user_global_section_accepts_server_settings`: the same table at the top
    level passes `user_config_schema`.

  `tests/config/test_filters.py`:
  - `test_absolute_host_path_pass_none` and `test_server_volume_map_pass_none`.
  - `test_absolute_host_path_keeps_the_value_as_written`: `"~/Dev"` and `"/abs"`
    clean to themselves.
  - `test_absolute_host_path_rejects_relative`: `"rel"` and `"~bob/x"` give
    `[AbsoluteHostPath.CODE_NOT_ABSOLUTE]`.

  `tests/config/sources/test_project_toml.py`:
  - `test_server_settings_are_discarded_before_validation`: a project file with
    `[agents.y]` `extra_args = ["-a"]` and `[agents.y.server]` `imge = 1` loads
    valid, `cleaned_data["agents"] == {"y": {"extra_args": ["-a"]}}`, and
    `result.discarded == ["agents.y.server"]`.
  - `test_nothing_discarded_without_server_settings`: `discarded == []`.
  - `test_non_table_agents_is_left_for_validation`: a project file `agents = 1`
    loads invalid with today's error at `agents`, and does not raise.

  `tests/config/test_loader.py`:
  - `test_project_file_server_settings_warn_and_are_ignored`: with
    `project_toml = true`, the project file above resolves without error, the
    resolved config has no `agents.y.server`, and the WARNING messages include
    exactly `project_toml: ignored agents.y.server — server settings are read only
    from the global section of your user config`.
  - `test_disabled_project_file_server_settings_draw_no_such_warning`: the same file
    with `project_toml` left disabled logs no message containing
    `server settings are read only`.
  - `test_user_server_settings_reach_the_merged_config`: user-level
    `[agents.y.server]` `image = "img"` resolves with
    `config["agents"]["y"]["server"]["image"] == "img"`.
  - `test_settings_warn_per_registry`: with fakes where `y` is a server only and
    `c` a client only, user config sets `agents.y.extra_args`, `agents.y.server`,
    `agents.c.extra_args` and `agents.c.server`. The WARNING messages are exactly,
    in this order:
    `[agents.c.server] No server named "c" is installed, so its settings are
    ignored; installed servers: y` and
    `[agents.y] No agent named "y" is installed, so its settings are ignored;
    installed agents: c, claude, false`. Build the fakes so those lists are exact.
    Names are reported in sorted order, and for one name `extra_args` before
    `server`. The existing `extra_args` message text does not change.
  - `test_server_settings_warning_reads_none_without_servers`: with the real, empty
    server registry, user-level `[agents.claude.server]` `image = "i"` warns
    `[agents.claude.server] No server named "claude" is installed, so its settings
    are ignored; installed servers: none`.
  - `test_matching_projects_entry_with_server_settings_stops_the_run`: a
    `[projects]` entry for the workdir holding `agents.y.server` raises the
    `ExceptionGroup`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/config -q --continue-on-collection-errors`
  Expected: `test_filters.py` errors at collection (it imports `AbsoluteHostPath`
  and `ServerVolumeMap`); the new schema, source and loader tests FAIL.

- [ ] **Step 3: Implement**

  - A filter class `AbsoluteHostPath` in `filters.py`: after `f.Unicode`, the value
    must be absolute once a first segment of exactly `~` is expanded, else a new code
    `CODE_NOT_ABSOLUTE` with template `"Path {value!r} must be absolute: a shared
    server's paths cannot depend on the workdir."`. It returns the value as
    written and touches no disk.
  - A filter class `ServerVolumeMap` in `filters.py`, modelled on `VolumeMap`: keys
    through `f.Unicode | AbsoluteHostPath`, values through
    `Volume(home_dir=CONTAINER_HOME)`; returns `dict[str, VolumeSpec]` keyed as
    written.
  - `_server_settings_schema` in `schema.py`: a `FilterMapper` of `build` (the
    `_build_schema` shape with `context` and `dockerfile` as
    `f.Unicode | AbsoluteHostPath`), `image` (`f.Unicode | f.NotEmpty`), `port`
    (`f.Type(int, allow_subclass=False) | f.Min(1) | f.Max(65535)`) and `volumes`
    (`ServerVolumeMap`); `allow_extra_keys=False`, `allow_missing_keys=True`.
  - `_agents_schema` becomes a function of `server_settings`; thread the flag
    through `_standard_fields` and `standard_config_schema`. `user_config_schema`
    takes no new parameter: it passes `server_settings=True` to `_standard_fields`
    for the global section and leaves `project_entry_schema` at the default.
  - `ProjectTomlSource.load`: decode the TOML first; remove each
    `agents.<name>.server` and record its dotted path in `discarded`, skipping
    wherever `agents` or `agents.<name>` is not a table so validation reports it as
    today; then validate what remains. An undecodable file is reported as today.
  - `ConfigLoader._sanitise`: for each enabled source, log one WARNING per
    `discarded` path with the text the loader test pins.
  - `ConfigLoader._warn_unknown_agent_settings`: judge per setting, as the Global
    Constraints say, with `installed_server_keys`-style lists built from the
    injected registries.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 4: Pair the client and the server

**Files:**
- Create: `src/paddock/agents/pairing.py`, `src/paddock/agents/errors.py`
- Modify: `src/paddock/__main__.py`
- Test: `tests/agents/test_pairing.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `ResolvedConfig.agent_key` and `server_key` (Task 2); the registries
  (Task 1).
- Produces, in `paddock.agents.errors`: `class AgentError(Exception)`, whose
  `str()` is the full user-facing line.
- Produces, in `paddock.agents.pairing`:
  `@dataclass(frozen=True) class AgentPairing` with `client: BaseAgent`,
  `server: BaseServer | None`, property `is_paired -> bool` (a server is present
  and both `PROTOCOL`s are the same non-`None` value), and
  `@classmethod resolve(cls, client_key: str, server_key: str | None, *, agents=agent_registry, servers=server_registry) -> AgentPairing`,
  which raises `AgentError` with exactly these messages, checked in this order:
  - unknown client: `[agent] Unknown agent "<key>"; installed agents: <list>`
    (today's text, unchanged).
  - unknown server: `[agent.server] Unknown server "<key>"; installed servers:
    <list>`, the list reading `none` when empty.
  - a client with a `PROTOCOL` and no server: `[agent] Agent "<client>" needs a
    server that speaks "<protocol>", but none is chosen; set agent.server`.
  - a client with a `PROTOCOL` and a server with another: `[agent] Agent "<client>"
    needs a server that speaks "<protocol>", but server "<server>" speaks
    "<its protocol>"`.

- [ ] **Step 1: Write the failing tests**

  `tests/agents/test_pairing.py`, with fake registries (a client `paired` and a
  server `srv` sharing protocol `p`; a server `other` with protocol `q`; a client
  `plain`):
  - `test_matching_protocols_are_paired`: `resolve("paired", "srv")` has
    `is_paired is True` and instances of both classes.
  - `test_plain_client_alone`: `resolve("plain", None)` has `server is None`,
    `is_paired is False`.
  - `test_plain_client_beside_a_server_is_not_paired`: `resolve("plain", "srv")`
    has the server instance and `is_paired is False`.
  - One test per message above, asserting `str(exc.value)` in full:
    `resolve("nope", None)`, `resolve("plain", "nope")`, `resolve("paired", None)`,
    `resolve("paired", "other")`.
  - `test_unknown_server_lists_none_when_empty`: with an empty server registry the
    message ends `installed servers: none`.

  `tests/test_main.py`:
  - Keep `test_unknown_agent_exits_one` passing unchanged.
  - `test_unknown_server_exits_one`: its own user config, `image = "ubuntu:22.04"`,
    `agent = { server = "nope" }` and `[config.allowlist] project_toml = true`,
    as `test_unknown_agent_exits_one` does: `.paddock` is only ever created with
    the project file enabled, so without that grant the last assertion could not
    fail. `run(["--dry-run"])` exits 1, stderr is exactly
    `[agent.server] Unknown server "nope"; installed servers: none`, and
    `.paddock` does not exist.
  - `test_cli_server_override_is_checked`: `run(["--dry-run",
    "--agent-server=nope"])` exits 1 with the same line.
  - `test_server_false_runs_without_one`: `agent = { client = "claude", server =
    false }`; `run(["--dry-run"])` exits 0.
  - `test_installed_server_cannot_start_yet`: call `_resolve_pairing` directly with
    fake registries holding a plain client and a server `srv`; it exits 1 and stderr is
    exactly `[agent.server] Server "srv" cannot be started by this version of
    paddock`.
  The other two `run` tests use the `minimal_config` fixture, so a missing image is
  not what stops them.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/agents/test_pairing.py tests/test_main.py -q --continue-on-collection-errors`
  Expected: `test_pairing.py` errors at collection, as does `test_main.py` if it
  imports `_resolve_pairing` at module level; otherwise the new `test_main` tests
  FAIL, except `test_server_false_runs_without_one`, which may pass already, as
  `test_unknown_agent_exits_one` does.

- [ ] **Step 3: Implement**

  - `errors.py` and `pairing.py` as specified.
  - `__main__.py`: replace `_resolve_agent` with
    `_resolve_pairing(agent_key: str, server_key: str | None, *, agents=agent_registry, servers=server_registry) -> AgentPairing`,
    which calls `AgentPairing.resolve`, prints an `AgentError` to stderr and exits
    1. `run` calls it before `ProjectDirManager` is entered and passes
    `pairing.client` wherever the agent instance was used.
  - Until the second half of this pull request lands there is nothing to start a
    server with. In the same helper, where `pairing.server` is not `None`, print
    `[agent.server] Server "<key>" cannot be started by this version of paddock`
    and exit 1. The helper takes `agents=` and `servers=` keywords like everything
    else that consults a registry. Mark the line with a comment naming ADR 019 as
    what replaces it.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 5: Check end to end, then retire the plan

**Files:**
- Delete: `docs/superpowers/plans/2026-11-16-agent-halves-and-pairing.md`

- [ ] **Step 1: Run a real container** with the `e2e-testing` skill (preflight
  first), matching at line start. Scenario config: the skill's base image and
  `agent = "claude"`. These scenarios are about the agent itself, the case the
  skill allows for passing arguments after `--` in place of a positional command,
  which would replace the agent's command whichever client is chosen (ADR 007).
  - `paddock --agent-client=false -- -c 'echo HALF_OK'` must exit 0 with one
    `^HALF_OK` line: the client half alone switched the container to the shell,
    which ran `/bin/bash -c 'echo HALF_OK'`.
  - Prove that check can fail: the same command without `--agent-client=false`
    must print no `^HALF_OK` line, since the container then runs
    `claude -c 'echo HALF_OK'`, which the base image lacks. Confirm with
    `--dry-run` that its argv ends `claude -c 'echo HALF_OK'`.
  - `paddock --agent=false --agent-server=nope -- -c 'echo NO'` must exit 1, print
    the unknown-server line, and print no `^NO` line.

- [ ] **Step 2: Run the whole suite on every supported Python**

  Run: `uv run tox run-parallel` and `uv run pytest --collect-only -q | tail -1`
  Expected: every environment passes; the count is above 364.

- [ ] **Step 3: Delete this plan file** and commit the deletion. Run `git status` to
  catch any related unstaged or untracked files, then use the
  `phx:creative-commits` skill. Push, then open the pull request against
  `develop`. Its description must say that user docs for `agent` as a table and for
  server settings land with the second half, before any release, and that a
  server-choosing run stops by design until then. Have a subagent read the
  description from a scratch file as a reviewer would before posting it.

## Intentional Decisions

*(Populated during review — reviewers must not re-raise these)*

- No user documentation in this plan. No bundled server exists yet, so the docs
  would describe settings nothing uses; they land with the second half.
- `UNNAMED_SERVER` is a plain string a user could write as `server = "<default>"`.
  It then means what it says, so nothing guards against it.
- On-disk checks of a server's paths belong to the second half, where a chosen
  server's settings are consumed (ADR 019: checked only when that server is chosen).
- The merged `config["agent"]` is a table. Tests that asserted the scalar are
  updated, not shimmed.
- A server-choosing run stops with a temporary message until the second half lands.
- ADR 018's "the log says so", for a no-protocol client beside a server, is built
  in the second half: no such run gets as far as logging in this one.
- `test_server_registry_is_empty_without_plugins` will need changing when the
  second half registers a bundled server; its docstring says so.

## Self-Review Checklist

- Does the plan header include a `**Worktree:**` field naming the existing worktree
  and branch?
- Does every commit step remind the agent to run `git status` first?
- Does the plan include an Intentional Decisions section?
- Does the final task delete the plan file?
- Does each Global Constraint have a test in Tasks 1 to 4?
- Does each Review Focus line have a named test in the task it cites?
