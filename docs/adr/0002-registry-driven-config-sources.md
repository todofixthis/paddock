---
status: Accepted
date: 2026-06-17
tags: [architecture, config, config-sources, registry]
summary: Load configuration through a registry-driven ConfigSource architecture with a source-owned LoadResult boundary, replacing the monolithic flat loader.
---

# 0002: Registry-Driven Config Source Architecture

## Context

paddock currently loads configuration from a flat merge of env vars, CLI flags, and a
single user-level TOML file. The loader is monolithic: it hard-codes a merge order, owns
env validation, and will be difficult to extend when new sources (e.g. project-level
config) are needed. Adding a source today means editing the loader, the merge order, and
any shared constant that lists known sources.

## Options

### Option 1: Do nothing

Keep the monolithic loader; add new sources as special cases inside it.

**Pros:** No new complexity.
**Cons:** Every new source grows a central function; merge order and validation stay
entangled.
**Risks:** Deferred forever — the current code is already hard to extend and the demand
for more sources exists.

### Option 2: Registry-driven source architecture (Accepted)

Each logical config source is a `ConfigSource` subclass that auto-registers into a
`SortedClassRegistry` keyed by `SOURCE_KEY` and ordered by `WEIGHT`. The loader iterates
the registry to load, sanitise, and merge; adding a source means only defining a new
class. Each source owns its own `LoadResult(instance, meta)` — the validated
`FilterRunner` instance and a plain `meta` dict — so no central code needs to know a
source's internal shape.

A four-phase workflow — **load → collect-and-validate → sanitise → reduce** — separates
concerns cleanly. Per-source validation uses a non-strict
`standard_config_schema(merged=False)` (required fields allow `None`); the final merge
pass uses a strict `standard_config_schema(merged=True)`.

**Pros:** Adding a source is a one-file change; no shared constant to update.

**Cons:**
- More files and indirection than the current flat loader.
- Two-mode schema macro is non-obvious at first read.

**Risks:**
- `SortedClassRegistry` (from `class_registry`) is an external dependency; its
  `AutoRegister` + `is_abstract()` contract must be preserved. The same maintainer owns
  `class_registry`, so upstream changes can be requested if the contract needs to move.
- Registration is an import side-effect: a source class registers only when its module
  is imported. A source module never imported silently never registers, with no error —
  the sources package must import every source module.

### Option 3: Plugin list with manual dispatch

Keep sources as separate functions, but dispatch through an explicit ordered list
maintained in the loader (no auto-registration).

**Pros:** No external registry dependency; dispatch order is visible in one place.
**Cons:** The ordered list is exactly the shared constant Option 2 avoids — every new
source still requires a loader edit.
**Risks:** The list and the source definitions drift apart over time (a source removed
from the list but not deleted, or vice versa).

## Decision

Option 2. The registry means the loader never needs to change when a new source is
added — only a new subclass is needed — which directly satisfies the project's
registry-driven extensibility convention. The source-owned `LoadResult` boundary keeps
each source's validation logic local instead of leaking into the loader.

Subsidiary decisions recorded here to avoid re-litigation:

- **Declarative `CONFIG_FIELDS` is the single source of truth for the standard config key
  structure** (`fields.py`). Each top-level key maps to its nested keys (empty tuple for
  a leaf). `allowlist_directives()` derives the valid dotted paths from `CONFIG_FIELDS`
  rather than reflecting into `filters`' private `_filters` internals. `schema.py` is
  hand-written and checked against `CONFIG_FIELDS` by a co-location test, so the schema
  and the allowlist directive list cannot silently diverge.

- **`ConfigError` in `paddock/config/errors.py`** — extracted to break circular imports
  between the loader and schema modules. Prefer restructuring module boundaries over
  deferred (`function-body`) imports; this extraction is the pattern for future cases.

- **`ConfigContext` frozen dataclass** — a single immutable object passed to every
  `ConfigSource.load(context)`. Keeps constructor signatures uniform; sources pick what
  they need. `@property project_key` instead of `@cached_property` because
  `frozen=True` forbids writable instance state.

- **`ConfigSource` inherits `ABC` explicitly** — `AutoRegister` skips classes whose
  `is_abstract()` returns `True`, which requires both ABC inheritance *and* an
  unimplemented `@abstractmethod`. Without `ABC` the registry would try to register
  the base class itself.

- **`SortedClassRegistry(sort_key="WEIGHT")` uses the string form** — a callable
  `sort_key` receives a `(key, class, lookup_key)` tuple, not just the class; a
  one-arg lambda crashes. The string form converts internally to `getattr(cls, "WEIGHT")`.

- **Two-mode `standard_config_schema(merged)`** — one macro serves both per-source
  (every required field allows `None`, optionals default to `None` so they don't
  pollute the merge) and final-merge (required fields reject `None`, optionals use
  their conventional defaults). `DropEmpty` strips absent fields so per-source results
  merge cleanly.

- **`LoadResult.meta` is a plain dict, valid by construction.** A malformed `[config]`
  invalidates the *instance* runner first (the meta schema is embedded in the
  file-level schema), so meta never needs a separate validity check.

- **`.paddock` lifecycle** — `ProjectDirManager` (a context manager) creates `.paddock`
  if missing, produces a `VolumeSpec` for a same-path bind mount (host path == container
  path, consistent with paddock's convention), and removes the directory post-exit only
  if paddock created it and it remains empty. The same-path mount exposes the host's
  absolute project path inside the container and works only where that path is valid in
  both namespaces. Mount mode defaults to read-only (`project_dir_readonly = true`) so
  the container cannot mutate host-side project state.

Allowlist gating of *which keys* an untrusted source may contribute — including the
`project_toml` off-by-default posture — is a separate security decision; see
[0003](0003-allowlist-over-denylist.md).

## Consequences

- Every config source is now an independently testable class; the test surface grows
  proportionally.
- The loader has no hard-coded merge order or source list; adding a source is a one-file
  change.
- `_env_schema` (previously a top-level constant in `schema.py`) moves into
  `EnvConfigSource`; any direct import of `_env_schema` from `schema.py` will break.
- The loader now returns `ResolvedConfig` (a dataclass) instead of a bare `dict`.
  Call sites in `__main__.py` must be updated.
