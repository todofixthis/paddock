# Agents Table and `extra_args` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user can set `agents.<name>.extra_args` in config and have those arguments
appended to that agent's command on every run.

**Architecture:** `agent` keeps choosing the agent. A new top-level `agents` table,
keyed by agent registry key, holds per-agent settings; this plan adds one,
`extra_args`. The schema validates its shape, the existing deep merge replaces the
list between sources, and `__main__` looks up the chosen agent's list and passes it
to `DockerCommandBuilder` ahead of the command line's agent args. Completed pre-work:
ADR 017 (`docs/adr/017-configure-agents-in-an-agents-table.md`) is committed on the
branch (`53df2bb`) and states every rule below. This plan file is committed too.

**Tech Stack:** Python, phx-filters, phx-class-registry, pytest, Sphinx with MyST.

**Spec:** `docs/superpowers/specs/2026-11-15-agent-client-server-design.md`, section
"`agents.<name>`", `extra_args` bullet only, and Delivery item 1. Nothing about
servers, `agent` as a table, or host-run clients belongs to this plan.

**Worktree:** `/home/user/paddock` (branch: `claude/laughing-knuth-e8mouz`). A cloud
session's container is already isolated and may push only to this branch, so no
separate worktree exists.

## Global Constraints

- `<name>` under `agents` is an agent's registry key, the string `agent` takes
  (`claude`, `false`, or a plugin's entry-point name). Every source accepts any name.
  After the merge, each name no installed agent has draws one warning listing the
  installed agents, and its settings are ignored. It is never a validation error.
- `extra_args` is a list of strings, passed verbatim. A string, or a list holding a
  non-string, is a validation error. Any other key under `agents.<name>` is a
  validation error.
- Command order: `[*agent.get_command(), *extra_args, *agent_args]`. `extra_args`
  never reaches Paddock's own flags.
- A replacement command ignores `extra_args` (ADR 007).
- A higher source's list replaces a lower one's; `[]` clears it.
- No environment-variable or CLI form.
- `agents` is one allowlist directive with no dotted children.
- Commit with `uv run git commit`, from the repo root. NZ English. Flat test
  functions, no lambdas in `parametrize`, Google-style docstrings, comments on the
  line above.
- The suite collects 335 tests before this plan; the count must rise.

## Review Focus

1. `extra_args = "--plugin-dir=./"` (a string, the natural first guess): a validation
   error naming `agents.<name>.extra_args`, not a list of single characters. Task 1.
2. An argument holding a space or shell metacharacter: one argv token, and the printed
   `--dry-run` line stays re-runnable. Task 2.
3. `agent = false` with `[agents.false]`: the boolean choice finds the string-keyed
   settings. Task 2.
4. `--agent=x` on the command line while config holds settings for both `x` and the
   configured agent: only `x`'s arguments apply. Task 2.
5. `[agents.claud]` (a typo): the run goes ahead, and a warning names `claud` and
   the installed agents. Task 2.

## File Map

- `src/paddock/config/schema.py`: the `agents` schema, wired into `_standard_fields`.
- `src/paddock/config/fields.py`: `agents` in `CONFIG_FIELDS`.
- `src/paddock/__main__.py`: looks up the chosen agent's `extra_args`, warns about
  unknown names. `src/paddock/docker/builder.py` is read, not changed.
- `tests/config/test_schema.py`, `tests/config/test_fields.py`,
  `tests/config/test_loader.py`, `tests/test_main.py`.
- `docs/usage/configuration.md`, `docs/usage/project-config.md`, `README.rst`.

---

### Task 1: Validate and merge the `agents` table

**Files:**
- Modify: `src/paddock/config/schema.py`, `src/paddock/config/fields.py`
- Test: `tests/config/test_schema.py`, `tests/config/test_fields.py`,
  `tests/config/test_loader.py`

**Interfaces:**
- Produces: the merged config may hold
  `config["agents"]: dict[str, dict[str, list[str]]]`, e.g.
  `{"claude": {"extra_args": ["--resume"]}}`. The key is absent when nothing sets it
  (`DropEmpty` strips an empty table), so readers use `config.get("agents", {})`.

- [ ] **Step 1: Write the failing schema tests** in `tests/config/test_schema.py`,
  with `assert_filter_passes` / `assert_filter_errors` on
  `standard_config_schema(base_dir=Path.cwd(), merged=False)`. Not the file's
  `_validate()` helper, which cannot assert an error key. Pass `skip_value_check` as
  the last argument to every `assert_filter_errors` call, as the file's existing
  error tests do; the `assert_filter_passes` tests compare against the input value:

  - `test_agents_accepts_extra_args`:
    `{"agents": {"claude": {"extra_args": ["--resume", "a b", ""]}}}` cleans to the
    same value.
  - `test_agents_accepts_a_name_no_agent_has`: `{"agents": {"claud": {"extra_args":
    ["-x"]}}}` is valid and cleans to itself.
  - `test_agents_keeps_an_empty_list`: `{"agents": {"claude": {"extra_args": []}}}`
    cleans to itself; the `[]` is not stripped.
  - `test_agents_rejects_a_string_extra_args`: `extra_args = "--resume"` gives
    `{"agents.claude.extra_args": [f.Type.CODE_WRONG_TYPE]}`.
  - `test_agents_rejects_a_non_string_entry`: `extra_args = ["a", 1]` gives
    `{"agents.claude.extra_args.1": [f.Type.CODE_WRONG_TYPE]}`.
  - `test_agents_rejects_an_unknown_setting`: `{"agents": {"claude": {"server":
    {}}}}` gives `{"agents.claude.server": [f.FilterMapper.CODE_EXTRA_KEY]}`.
  - `test_agents_rejects_a_non_table`: `{"agents": "claude"}` gives
    `{"agents": [f.Type.CODE_WRONG_TYPE]}`. Today the code is "unexpected key", so
    the exact code is what makes this fail first.
  - `test_allowlist_entry_rejects_a_path_under_agents`, beside
    `test_allowlist_entry_rejects_unknown_dotted_path`: `AllowlistEntry` on
    `["agents.claude"]` gives `{"0": [f.Choice.CODE_INVALID]}`. This one passes
    before and after; it pins "no dotted children".
  - `test_project_entry_accepts_agents`: a user config TOML string with
    `[projects."/x".agents.claude]` and `extra_args = ["--resume"]` passes
    `user_config_schema`.

  In `test_every_directive_is_accepted_by_the_schema`, add `"agents"` to
  `mapping_valued`. In `tests/config/test_fields.py`, add `"agents"` to the set in
  `test_directives_include_top_level_keys`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/config/test_schema.py tests/config/test_fields.py -q`
  Expected: the new tests FAIL (`agents` is an unexpected key, or missing from the
  directives), except `test_allowlist_entry_rejects_a_path_under_agents`; every
  other test passes.

- [ ] **Step 3: Implement**

  In `src/paddock/config/fields.py`, add `"agents": ()` to `CONFIG_FIELDS`, in
  alphabetical position.

  In `src/paddock/config/schema.py`, add a module-level `_agents_schema`:
  `f.Type(dict) | f.FilterRepeater(f.FilterMapper({"extra_args": f.Array |
  f.FilterRepeater(f.Type(str))}, allow_extra_keys=False,
  allow_missing_keys=True))`. `f.Type(str)`, not `f.Unicode`: `f.Unicode` coerces `1`
  to `"1"`. The schema must not consult the agent registry (ADR 017). In
  `_standard_fields`, add `"agents": _agents_schema` in alphabetical position.
  Because `_standard_fields` feeds `standard_config_schema`, `project_entry_schema`
  and `user_config_schema`, no other schema needs editing.

- [ ] **Step 4: Run the schema and fields tests**

  Run: `uv run pytest tests/config/test_schema.py tests/config/test_fields.py -q`
  Expected: PASS.

- [ ] **Step 5: Write the loader tests** in `tests/config/test_loader.py`, using that
  file's existing helpers for writing a user config and calling
  `ConfigLoader.resolve`:

  - `test_project_override_replaces_extra_args`: global
    `[agents.claude] extra_args = ["--a", "--b"]` and
    `[projects."<workdir>".agents.claude] extra_args = ["--c"]` resolve to
    `config["agents"]["claude"]["extra_args"] == ["--c"]`.
  - `test_project_override_clears_extra_args`: the project entry sets `[]`; the
    resolved list is `[]`.
  - `test_agents_settings_merge_per_agent`: global sets `agents.claude`, the project
    entry sets `agents.false`; both survive.
  - `test_another_projects_agents_entry_does_not_apply`: a `[projects]` entry for a
    different path sets `agents.claude.extra_args`; the resolved config has no
    `agents`.
  - `test_env_cannot_set_agents`: `PADDOCK_AGENTS_CLAUDE_EXTRA_ARGS=x` in `environ`
    raises the `ExceptionGroup` (an unknown `PADDOCK_*` name).
  - `test_project_toml_agents_dropped_unless_allowlisted`: with
    `[config.allowlist] project_toml = ["volumes"]` and a `.paddock/config.toml`
    holding `[agents.claude] extra_args = ["--x"]`, the resolved config has no
    `agents` and the warning names `agents`.
  - `test_project_toml_agents_kept_when_allowlisted`: the same project file under
    `project_toml = ["agents"]` resolves with
    `config["agents"]["claude"]["extra_args"] == ["--x"]`.
  - `test_user_extra_args_beat_the_project_file`: with `project_toml = true`, the
    user config sets `agents.claude.extra_args = []` and the project file sets
    `["--x"]`; the resolved list is `[]`.

- [ ] **Step 6: Run the loader tests**

  Run: `uv run pytest tests/config/test_loader.py -q`
  Expected: PASS with no loader change. `_deep_merge` already replaces a list and
  merges tables, so these pin existing behaviour and never go red by themselves. If one fails, fix the cause in the schema or loader; do not weaken
  the test.

- [ ] **Step 7: Type-check, lint and run everything**

  Run: `uv run mypy src/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 8: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then `git push`.

### Task 2: Append `extra_args` to the agent's command

**Files:**
- Modify: `src/paddock/__main__.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `config.get("agents", {})` from Task 1, and
  `DockerCommandBuilder.build(*, command, agent_args)`, unchanged, which already
  appends `agent_args` and ignores them when `command` is non-empty.
- The lookup key is the registry key `_resolve_agent` already derives: `"false"`
  when `config["agent"]` is the boolean `False`, else `str(config["agent"])`. Not
  `agent.AGENT_KEY`, which a plugin may set differently from its entry-point name.

- [ ] **Step 1: Write the failing tests** in `tests/test_main.py`, following
  `test_dry_run_prints_a_re_runnable_command`. Each parses the printed line with
  `shlex.split`:

  - `test_dry_run_applies_extra_args_from_config`: a user config with
    `[agents.claude] extra_args = ["--append-system-prompt", "be brief; no $HOME"]`;
    `run(["--dry-run", "--", "fix it"])` prints an argv ending
    `["claude", "--append-system-prompt", "be brief; no $HOME", "fix it"]`.
  - `test_replacement_command_ignores_extra_args`: the same config;
    `run(["--dry-run", "/bin/bash"])` prints an argv ending `["/bin/bash"]` with no
    `--append-system-prompt` in it.
  - `test_shell_agent_uses_its_own_extra_args`: `agent = false` with
    `[agents.false] extra_args = ["-l"]` and `[agents.claude] extra_args =
    ["--resume"]`; the printed argv ends `["/bin/bash", "-l"]`.
  - `test_cli_agent_switch_uses_that_agents_extra_args`: the same config with
    `agent = "claude"`; `run(["--dry-run", "--agent=false"])` prints an argv ending
    `["/bin/bash", "-l"]`.
  - `test_no_agents_table_leaves_the_command_alone`: the minimal config;
    `run(["--dry-run"])` prints an argv ending `["claude"]`.
  - `test_unknown_agent_settings_warn_and_run`: `[agents.claud] extra_args = ["-x"]`
    and `[agents.false] extra_args = ["-l"]` with `agent = "claude"`. Wrap `run` in
    `with caplog.at_level(logging.WARNING, logger="paddock"):`, as
    `test_logs_every_mounted_volume` does: an earlier `--quiet` test disables
    logging for the whole process, and `at_level` re-enables it. The run exits 0,
    the printed argv ends `["claude"]`, and the WARNING records' messages are
    exactly `['[agents.claud] No agent named "claud" is installed, so its settings
    are ignored; installed agents: claude, false']`. One record: the installed
    `false` draws none, and asserting the whole message stops `claud` matching
    inside `claude`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/test_main.py -q`
  Expected: the `applies_extra_args`, `shell_agent`, `cli_agent_switch` and
  `unknown_agent_settings` tests FAIL. The `replacement_command` and
  `no_agents_table` tests pass already and pin existing behaviour.

- [ ] **Step 3: Implement** in `src/paddock/__main__.py`, in that module's existing
  style of private helpers with docstrings:

  - `_agent_key(configured: str | bool) -> str`: the key derivation lifted out of
    `_resolve_agent`, which then calls it.
  - `_extra_args(config: dict, agent_key: str) -> list[str]`: returns
    `config.get("agents", {}).get(agent_key, {}).get("extra_args", [])`. Docstring
    cites ADR 017.
  - `_warn_unknown_agent_settings(config: dict) -> None`: for each key of
    `config.get("agents", {})` not among the registry's keys, in sorted order,
    `logger.warning('[agents.%s] No agent named "%s" is installed, so its settings
    are ignored; installed agents: %s', ...)`. Build the installed list with one
    helper, `_installed_agents() -> str`, and have `_resolve_agent`'s error use it
    too. The helper is for the message only: membership is
    `name not in agent_registry`.
  - In `run`, call `_warn_unknown_agent_settings(config)` straight after
    `_resolve_agent`, and pass `agent_args=[*_extra_args(config,
    _agent_key(config["agent"])), *parsed.agent_args]` to `command_builder.build`.

- [ ] **Step 4: Run the tests**

  Run: `uv run mypy src/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then `git push`.

### Task 3: Document `agents`

**Files:**
- Modify: `docs/usage/configuration.md`, `docs/usage/project-config.md`, `README.rst`

- [ ] **Step 1: Write the docs**

  `docs/usage/configuration.md`:

  - Reference table: an `agents.<name>.extra_args` row after `agent`. User config:
    `[agents.claude]` then `extra_args = ["--resume"]`. Per-project override:
    `[projects."<workdir>".agents.claude]`. Project file: `[agents.claude]`.
    Environment and command line: 🚫.
  - A `### agents.<name>.extra_args` section after `### agent`, covering every Global
    Constraint above in user terms, with these examples: the per-project
    `--plugin-dir=./` case; a project clearing a global list with `[]`; and the
    printed command for `paddock -- "fix it"` showing the order. State that the
    command line's equivalent is the tokens after `--`.
  - Troubleshooting: an entry for the unknown-agent-settings warning. Copy the exact
    text from a real run, not from this plan. Say that `--quiet` hides it.

  `docs/usage/project-config.md`, The allowlist: say that `agents` is a single
  directive covering every agent's settings. Add one `CAUTION` alert, in the form
  `.agents/rules/docs-alerts.md` requires, with the bold line
  `**Allowlisting agents lets a project file pass arguments to your agent**`:
  an argument can switch off an agent's own safeguards (Claude Code's
  `--dangerously-skip-permissions`), so allowlist `agents` only for projects whose
  files you trust as much as your own config. Say that `project_toml = true` already
  includes it, and that a user-level `extra_args`, even `[]`, takes precedence over
  the project file's. Check that section has no alert
  already; the rule allows one per section.

  Passages `agents` makes stale, each to update:

  - `configuration.md`, `### config.allowlist`: the sentence listing every allowlist
    path gains `agents`.
  - `configuration.md`, `### Precedence`, "Merging is per key": an `agents` bullet.
    Settings merge per agent name; `extra_args` is replaced whole. Qualify "the
    project file can't override a value you set": a granted file can still add
    settings for an agent you have not configured.
  - `project-config.md`, the list weighing what each key hands a committed file: an
    `agents` bullet.
  - `project-config.md`, Warning behaviour: `agents` is reported as a single path,
    as `volumes` and `build.args` are.
  - `README.rst`, the sentence saying `volumes` and `build.args` add up across
    sources: say `agents` merges per agent while each `extra_args` list is replaced.

  `README.rst`, after the paragraph on `--` (near "everything after ``--`` is
  appended"): two sentences and one example saying a standing argument can live in
  config, linking the configuration page.

- [ ] **Step 2: Build the docs strictly**

  Run: `uv run make -C docs html SPHINXOPTS="-W --keep-going -E"`
  Expected: exit 0, no warnings.

- [ ] **Step 3: Run the writing passes** the user's global instructions require for a
  documentation file: an audience-surrogate review by a subagent reading the three
  files from disk as a Paddock user would, then `phx:nz-english` over them, then a
  conciseness re-read. Address or answer every finding.

- [ ] **Step 4: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then `git push`.

### Task 4: Check end to end, then retire the plan

**Files:**
- Delete: `docs/superpowers/plans/2026-11-15-agents-table-extra-args.md`

- [ ] **Step 1: Run a real container** with the `e2e-testing` skill (preflight first).
  Scenario: a clean `$HOME` whose user config sets the skill's base image,
  `agent = false` and `[agents.false] extra_args = ["-c", "echo EXTRA_OK"]`. Match at
  line start throughout, since the printed `docker run` line also contains the
  text. A real run must exit 0 with `grep -c '^EXTRA_OK'` equal to 1. A second run
  with a replacement command, `paddock /bin/echo REPLACED`, must give one
  `^REPLACED` line and no `^EXTRA_OK`. Prove the check can fail: change the list to
  `["-c", "echo OTHER"]`, rerun the first case, and confirm `^OTHER` is present and
  `^EXTRA_OK` absent. Do not remove the list instead: a bare interactive shell never
  exits under the skill's pseudo-TTY.

- [ ] **Step 2: Run the whole suite on every supported Python**

  Run: `uv run tox run-parallel` and `uv run pytest --collect-only -q | tail -1`
  Expected: every environment passes; the count is above 335.

- [ ] **Step 3: Delete this plan file** and commit the deletion. Run `git status` to
  catch any related unstaged or untracked files, then use the
  `phx:creative-commits` skill. Push, then open the pull request against `develop`. Its description must
  carry ADR 017's upgrade note for the release notes: a user with
  `project_toml = true` grants `agents` on upgrade without acting. Have a subagent
  read the description from a scratch file as a reviewer would before posting it.

## Intentional Decisions

*(Populated during review — reviewers must not re-raise these)*

- The design doc under `docs/superpowers/specs/` stays on the branch: it also covers
  the two later pull requests.
- No log line announces `extra_args`; the printed `docker run` line already shows
  them.
- The three helpers added to `__main__.py` are module-level functions, matching that
  module's existing style, despite the class-first rule elsewhere.
- `run` derives the agent key a second time rather than have `_resolve_agent`
  return it; one cheap pure call beats a wider return type.
- `[agents.""]` passes the schema and warns as `[agents.]`; `FilterRepeater` cannot
  check keys, and the warning already reports it.
- `[agents.claud]` with no keys under it is stripped as an empty table and draws no
  warning. Nothing was ignored, so nothing is reported.
- `f.Type(str)` rejects a TOML integer in `extra_args` rather than coercing it, so
  `true` never silently becomes `"True"`.

## Self-Review Checklist

- Does the plan header include a `**Worktree:**` field naming the existing worktree
  and branch?
- Does every commit step remind the agent to run `git status` first?
- Does the plan include an Intentional Decisions section?
- Does the final task delete the plan file?
- Does each Global Constraint have a test in Task 1 or Task 2?
- Does each Review Focus line have a named test in the task it cites?
