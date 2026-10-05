---
status: Accepted
date: 2026-06-17
scope: [src/paddock/config/allowlist.py, src/paddock/config/fields.py, src/paddock/config/filters.py, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/config/sources/]
summary: Gate untrusted config sources with a per-source allowlist (opt-in), not a denylist, and disable project_toml by default as its application.
---

# 004: Gate Untrusted Config Sources with an Allowlist

## Context

As project-level config (`.paddock/config.toml`) is introduced on top of the source
architecture in [ADR 003][], the risk of an untrusted source (a checked-in project file,
an unreviewed env override) silently taking over container behaviour — image, volumes,
network — increases. Project contributors must not be able to force arbitrary container
behaviour on team members simply by committing a `.paddock/config.toml`.

The threat model is a checked-in change from an untrusted contributor, not an
attacker-controlled shell: `env` and `cli` inputs are assumed to come from the operator
running paddock. This scoping determines which sources need gating and which don't.

## Options

### Option 1: Do nothing

No key-level gating; any source may set any config key once loaded.

**Pros:** No new complexity.
**Cons:** A checked-in `.paddock/config.toml` can silently redirect any team member's
container image, volumes, or network.
**Risks:** Security posture unchanged — the exact problem this decision exists to solve.

### Option 2: Allowlist, opt-in (Accepted)

Each source declares a per-class [`ALLOWLIST_DEFAULT`][] (`bool | list[str]`); the base
class defaults it to `False`, so a new source starts blocked. An [`Allowlist`][], built
from these class defaults plus user-supplied `[config.allowlist]` rules, gates which
keys a source may contribute; keys with no rule are default-denied. The `user` source is
hard-wired always enabled, regardless of any rule — it is the operator's own trusted
file. `project_toml` defaults to blocked (`ALLOWLIST_DEFAULT = False`) as a direct
application of the generic rule: no special-cased code path, just the same mechanism any
source uses. Users opt in via `[config.allowlist]\nproject_toml = true`.

**Pros:** The same mechanism applies uniformly to `cli`, `env`, `extra`,
`project_overrides`, and `project_toml`.

**Cons:** A key the rule does not permit is dropped with a warning, not an error:
paddock names the dropped leaf paths whether the source is wholly or partly disabled,
but the run continues without the config the operator believed was applied, and
`--quiet` hides the warning altogether — a real debugging cost. (A mistyped *allowlist
entry* is a separate matter: it is rejected when the user config loads, with
`[user:config.allowlist.project_toml.0] Valid options are: […]`.)

### Option 3: Denylist

Maintain an explicit denylist of keys `project_toml` (or any untrusted source) may not
set; everything else is allowed.

**Pros:** Minimal structural change; no allowlist bookkeeping for trusted keys.
**Cons:** New config keys are implicitly trusted — the wrong default for a tool that
runs arbitrary containers.
**Risks:** Easy to forget to add a new dangerous key to the denylist; security posture
degrades silently as the schema grows.

## Decision

Option 2. Opt-in is the only viable default for a tool that runs arbitrary containers:
forgetting to block a new key is a security regression, forgetting to allow one is
merely inconvenient. Per-class `ALLOWLIST_DEFAULT` with default-deny fallback keeps the
gating generic — `project_toml`'s blocked default falls directly out of the same rule
that keeps `cli`, `env`, `extra`, and `project_overrides` trusted, with no gating code
specific to `project_toml`. The one deliberate exception is `user`, which the loader
hard-wires to always-enabled: it is the operator's own trusted file, so no rule may
disable it.

Subsidiary decisions recorded here to avoid re-litigation:

- **`extra` and `project_overrides` stay trusted (`ALLOWLIST_DEFAULT = True`) and are
  NOT user-restrictable.** The valid `[config.allowlist]` keys remain the static
  `{cli, env, project_toml}` ([`schema._ALLOWLIST_SOURCES`][schema.py]), not a
  registry-derived set, because `schema.py` is imported without `sources`; a
  registry-derived key set would be empty at schema-construction time and reject every
  allowlist key. Full per-source uniformity here is YAGNI.

- **`Allowlist` does not import `sources`; the loader injects the defaults.**
  `Allowlist(defaults, raw)` is pure data; the loader (which already imports
  `source_registry` at module level) builds the `{key: ALLOWLIST_DEFAULT}` map. This
  avoids a runtime `import sources` inside `Allowlist` that would cycle
  (`sources → base → allowlist → sources`).

- **`[config.allowlist]` valid globally and per-project** — `[config.allowlist]` in the
  user TOML applies to all projects; `[projects."<path>".config.allowlist]` shadows it
  on a per-source-key basis for that project only.

- **[`AllowlistEntry`][] defers [`allowlist_directives()`][] resolution** — the set of
  valid dotted paths (see ADR 003 for the declarative `CONFIG_FIELDS` source) is fetched
  at validation time, not import time, to avoid a circular import between `filters.py`
  and `schema.py`. This is the one permitted deferred-import location in this branch.

## Consequences

- `project_toml` is off by default — existing users who created `.paddock/config.toml`
  will need to opt in via `[config.allowlist]\nproject_toml = true`.
- Operators running paddock in CI, or any context where `PADDOCK_*` env vars are not
  fully trusted, must explicitly gate `env` via `[config.allowlist]` — the default
  assumes an interactively-operated shell.
- Because the valid allowlist keys are static rather than registry-derived, an operator
  auditing "what may `project_toml` set today" must read `ALLOWLIST_DEFAULT` across the
  source classes; there is no single enumerated list to consult.

[ADR 003]: 003-load-config-through-a-registry-of-sources.md
[`Allowlist`]: ../../src/paddock/config/allowlist.py
[`ALLOWLIST_DEFAULT`]: ../../src/paddock/config/sources/base.py
[`allowlist_directives()`]: ../../src/paddock/config/fields.py
[`AllowlistEntry`]: ../../src/paddock/config/filters.py
[schema.py]: ../../src/paddock/config/schema.py
