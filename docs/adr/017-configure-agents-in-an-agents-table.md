---
status: Accepted
date: 2026-11-15
scope: [README.rst, docs/usage/, src/paddock/__main__.py, src/paddock/agents/, src/paddock/cli.py, src/paddock/config/, src/paddock/docker/builder.py]
summary: Per-agent settings live in a top-level agents table keyed by the agent's registry key, separate from the agent key that chooses one (not nested under agent, and not a top-level extra_args); agents.<name>.extra_args is a list passed verbatim after the agent's command and before the tokens after --, replaced rather than concatenated by a higher source, ignored with a replacement command, with no environment or CLI form; agents is one allowlist directive with no dotted children; a name no installed agent has draws a warning after the merge, never a validation error.
revisit-when: Restating a whole list to change one entry proves costly, such as project lists drifting from the global one they copied; users need to drop standing extra_args for a single run; an agent setting needs an environment-variable or CLI form; an untrusted source needs to be allowlisted for one agent's settings, or one setting, and not the rest; misspelt agent names go unnoticed because the warning is missed.
---

# 017: Configure Agents in an Agents Table

## Context

An agent's command comes only from its class. Arguments a user always wants (a plugin
directory for Claude Code in one project, or the harness an Omnigent client should
launch) must be retyped after `--` on every run ([ADR 007][]).

Config has one agent key, `agent`: a string that chooses the agent, or `false` for
the shell. Planned work on agent servers needs more settings per agent, such as a
server's image and mounts, so whatever holds arguments will also hold those.

TOML cannot give one key both a string and a table: `agent = "omnigent"` beside
`[agent.omnigent]` does not parse, which Paddock reports as invalid TOML.

An unknown `agent` stops a run only when it is the merged value
([`_resolve_agent`][]). A config that names an agent in another project's entry, or
under a value another source overrides, works on a machine without that agent's package.

## Options

### Option 1: Do nothing

**Pros:** No new config surface.
**Cons:** Per-project arguments live in shell history or aliases, outside the config
that already varies by project.
**Risks:** Server settings, when they arrive, need this decision anyway.

### Option 2: A top-level `agents` table keyed by agent name (Accepted)

`agent` keeps choosing. `[agents.<name>]` holds that agent's settings, starting with
`extra_args`.

**Pros:** Settings for an agent that is not chosen stay in place, so a project
override or `--agent` switches agent without touching them.
**Cons:** Two keys one letter apart, both valid allowlist entries: a slip grants a
different power and passes validation.
**Risks:** A typo in the table name reads as an unknown top-level key, not as a
misspelt `agents`.

### Option 3: Nest the settings under `agent`

`[agent]` with `name = "omnigent"`, and `[agent.omnigent]` under it.

**Pros:** One key.
**Cons:** Agent names share a namespace with the table's own keys, so no agent can be
called `name`, and each key added later takes another name from third-party agents.
`agent = "claude"` and `[agent]` cannot share a scope, so a user adding their first
setting must also rewrite how they choose.
**Risks:** A third-party agent already published under a name Paddock later reserves
stops being configurable.

### Option 4: A top-level `extra_args`, not keyed by agent

**Pros:** The shortest config.
**Cons:** The arguments belong to one agent's command line. Choosing another agent for
one project or one run passes it the first agent's flags.
**Risks:** Server settings still need a per-agent home, leaving agent settings in two
places.

## Decision

Option 2. Arguments are meaningless to any agent but the one they were written for, so
they must be keyed by agent, which rules out Option 4. Option 3 keys them too, but
spends the agent namespace on Paddock's own keys and makes the common first edit a
rewrite.

`<name>` is the agent's registry key: the entry-point name, the same string `agent`
takes, with `false` for the shell. Every config file accepts any name. After the
merge, each name no installed agent has draws a warning listing the installed agents,
and its settings are ignored. A validation error would catch typos sooner, but every
enabled source is validated whole on every run ([ADR 004][], [ADR 014][]): one entry
for a plugin agent, in a committed project file or a user config shared between
machines, would stop every run wherever that plugin is missing, including runs of
another agent. `agent` already tolerates the same case.

For `extra_args`:

- **A list of strings.** A string would need quoting rules.
- **Passed verbatim**, apart from the Unicode normalisation every config string
  gets. No `~` expansion and no path resolution: an argument names a
  path in the container, so [ADR 012][] does not apply.
- **Appended** after the agent's command and before the tokens after `--`, so a
  one-off argument can follow a standing one. It never reaches Paddock's own flags.
- **Ignored with a replacement command**, as the tokens after `--` are under ADR 007:
  the agent's command is gone.
- **Replaced, not concatenated,** by a higher source. Concatenation would leave a
  project no way to drop a global argument; replacement lets it restate the list, and
  `[]` clears it.
- **No environment or CLI form.** `PADDOCK_*` names map to config paths by splitting on
  `_` ([`EnvConfigSource`][]), which breaks on `extra_args` and on a free-form agent
  name, and one variable holding a list needs the quoting rules the string form was
  rejected for. On the command line the tokens after `--` already add arguments.

`agents` is one allowlist directive (ADR 004), with no dotted children: its keys are
agent names, not schema fields.

## Consequences

- An untrusted source allowlisted for `agents` can set arguments for any agent the
  user's own config has not, and an argument can switch off an agent's own
  safeguards. A user-level `extra_args`, even `[]`, takes precedence over the project
  file. The project file stays disabled by default; the docs say what allowlisting
  `agents` grants.
- A user who already allowlists everything from a source (`project_toml = true`)
  grants `agents` on upgrade without acting. The release notes say so.
- Because the directive is whole, a later setting that an untrusted source must never
  set needs a gate of its own; allowlisting `agents` cannot be what protects it.
- Nothing on the command line drops a standing `extra_args` for one run, short of a
  replacement command that restates the agent's.
- A misspelt agent name is reported by a warning, which `--quiet` hides. The same
  warning repeats on every run on a machine that lacks a configured plugin, where
  only `--quiet` silences it, along with every other warning.
- ADR 007's grammar is unchanged: `extra_args` is appended, so its trigger (an agent
  needing arguments inserted) stays live.

[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 007]: 007-split-agent-args-from-replacement-command.md
[ADR 012]: 012-resolve-relative-config-paths-against-the-workdir.md
[ADR 014]: 014-check-host-paths-only-in-the-matching-projects-entry.md
[`EnvConfigSource`]: ../../src/paddock/config/sources/env.py
[`_resolve_agent`]: ../../src/paddock/__main__.py
