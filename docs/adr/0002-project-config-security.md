---
status: Accepted
date: 2026-06-17
tags: [config, security, architecture, registry, allowlist]
summary: Introduce a registry-driven config-source architecture with an allowlist mechanism and .paddock directory lifecycle management to secure project-level configuration.
---

# 0002: Secure Project-Level Config via Source Registry and Allowlist

## Context

paddock currently loads configuration from a flat merge of env vars, CLI flags, and a single
user-level TOML file. As project-level config (`.paddock/config.toml`) is introduced, the
risk of an untrusted source (a checked-in project file, malicious env override) silently
taking over container behaviour — image, volumes, network — increases.

Two forces are at play:

- **Security:** project contributors should not be able to force arbitrary container
  behaviour on team members simply by committing a `.paddock/config.toml`.
- **Ergonomics:** power users want project-level config to work, and the architecture
  must support per-project allowlisting without becoming a special case.

Separately, the existing loader is monolithic: it hard-codes a merge order, owns env
validation, and will be difficult to extend when new sources are needed.

## Options

### Option 1: Do nothing

Keep the monolithic loader; skip project-level config entirely.

**Pros:** No new complexity.
**Cons:** No project-level config; security posture unchanged.
**Risks:** Deferred forever — the demand exists and the current code is already hard to extend.

### Option 2: Registry-driven source architecture with allowlist (Accepted)

Each logical config source is a `ConfigSource` subclass that auto-registers into a
`SortedClassRegistry` keyed by `SOURCE_KEY` and ordered by `WEIGHT`. The loader
iterates the registry to load, sanitise, and merge. An `Allowlist` (built from trusted
sources) gates which keys each untrusted source may contribute. Project-level config
(`project_toml`) is disabled by default; users opt in via `[config.allowlist]`.

A four-phase workflow — **load → collect-and-validate → sanitise → reduce** — separates
concerns cleanly. Per-source validation uses a non-strict `standard_config_schema(merged=False)`
(required fields allow `None`); the final merge pass uses a strict `standard_config_schema(merged=True)`.

**Pros:**
- Security by default: new sources start blocked; the allowlist is small and auditable.
- Extensible: adding a source means defining a class; no central list to update.
- Testable: each source is a standalone class with its own test file.
- Generic blocking: disabled sources are treated identically regardless of type.

**Cons:**
- More files and indirection than the current flat loader.
- Two-mode schema macro is non-obvious at first read.

**Risks:**
- `SortedClassRegistry` (from `class_registry`) is an external dependency; its
  `AutoRegister` + `is_abstract()` contract must be preserved.

### Option 3: Flat loader with a denylist

Keep the monolithic loader; add an explicit denylist of keys project_toml may not set.

**Pros:** Minimal structural change.
**Cons:** Denylist must be manually maintained; new keys are implicitly trusted (wrong default).
**Risks:** Easy to forget to add a dangerous key; security posture degrades silently over time.

## Decision

Option 2. The registry architecture is chosen for three reasons:

1. **Allowlist over denylist** — opt-in is the only viable default for a tool that runs
   arbitrary containers. Forgetting to block a new key is a security regression; forgetting
   to allow one is merely inconvenient.
2. **Generic blocking** — the same allowlist mechanism applies to `env`, `cli`, and
   `project_toml`. There is no special-cased code path per source.
3. **Extensibility** — the registry means the loader never needs to change when a new
   source is added; only a new subclass is needed.

Subsidiary decisions recorded here to avoid re-litigation:

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

- **`AllowlistEntry` defers `allowlist_directives()` resolution** — the set of valid
  dotted paths is fetched at validation time, not import time, to avoid a circular
  import between `filters.py` and `schema.py`. This is the one permitted deferred-import
  location in this branch.

- **`[config.allowlist]` valid globally and per-project** — `[config.allowlist]` in the
  user TOML applies to all projects; `[projects."<path>".config.allowlist]` shadows it on
  a per-source-key basis for that project only.

- **`project_toml` disabled by default** — an application of the generic allowlist rule.
  No special-cased code; the same mechanism that could disable `env` or `cli` disables
  `project_toml`.

- **No tilde expansion in `[projects."<path>"]` keys** — deferred until
  [todofixthis/filters#92](https://github.com/todofixthis/filters/issues/92) (key-level
  filter support in `FilterMapper`). Project paths must be absolute resolved strings.
  The schema rejects relative or tilde paths.

- **`.paddock` lifecycle** — `ProjectDirManager` creates `.paddock` if missing, produces
  a `VolumeSpec` for a same-path bind mount (host path == container path, consistent with
  paddock's convention), and removes the directory post-exit only if paddock created it
  and it remains empty. Mount mode defaults to read-only (`project_dir_readonly = true`).

## Consequences

- Every config source is now an independently testable class; the test surface grows
  proportionally.
- The loader has no hard-coded merge order or source list; adding a source is a one-file
  change.
- `project_toml` is off by default — existing users who created `.paddock/config.toml`
  will need to opt in via `[config.allowlist]\nproject_toml = true`.
- `_env_schema` (previously a top-level constant in `schema.py`) moves into
  `EnvConfigSource`; any direct import of `_env_schema` from `schema.py` will break.
- The loader now returns `ResolvedConfig` (a dataclass) instead of a bare `dict`.
  Call sites in `__main__.py` must be updated.
