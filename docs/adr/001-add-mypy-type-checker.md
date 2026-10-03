---
status: Accepted
date: 2026-05-09
revisit-when: ty stabilises (leaves 0.0.x) and ships a published autohooks plugin.
scope: [.github/workflows/build.yml, pyproject.toml]
summary: Use mypy (not Astral ty) for static type checking via autohooks-plugin-mypy.
---

# 001: Add mypy as Type Checker

## Context

The project has no static type checking. It targets Python 3.12+ and uses autohooks
for pre-commit quality gates (black, ruff, pytest).

The [`phx-filters`][phx-filters] library has no `py.typed` marker or stubs, so any type
checker reports `import-untyped` (or equivalent) errors for its imports unless they are
suppressed.

## Options

### Option 1: Do nothing

Leave type checking to manual inspection and tests alone.

**Pros:** No setup cost; no false-positive noise.
**Cons:** Type errors reach review or runtime instead of pre-commit; no
type-grounded IDE feedback.
**Risks:** Regressions in type correctness are silent.

### Option 2: Add mypy (Accepted)

Add [mypy][] and [`autohooks-plugin-mypy`][] as dev dependencies. Configure a
`[[tool.mypy.overrides]]` section with `ignore_missing_imports` for the
`filters` package globally. Enable `check_untyped_defs` so that unannotated
methods (e.g. `_apply` overrides) are still checked.

**Pros:** Battle-tested; `autohooks-plugin-mypy` is published on PyPI (no
custom plugin needed).
**Cons:** Slower than newer checkers; second ecosystem alongside Astral
tooling (uv, ruff).
**Risks:** phx-filters gains types in a future release, making the override
redundant — low risk, easy to remove.

### Option 3: Add ty

Add the Astral [ty][] type checker. No published autohooks plugin exists,
requiring a project-local plugin.

**Pros:** Fits the Astral-native toolchain; very fast; zero-config.
**Cons:** Pre-release (0.0.x) — behaviour may change with each patch; no
published autohooks plugin; phx-filters DSL produces `invalid-argument-type`
false positives at every call site (requiring per-line suppression rather than
a single module-level override).
**Risks:** Tight version pinning required; upgrade friction while the tool is
still in flux.

## Decision

Use mypy. The published `autohooks-plugin-mypy` keeps the pre-commit
integration simple, and the per-module `ignore_missing_imports` override
cleanly suppresses phx-filters noise without touching call sites. ty's
ecosystem fit is appealing but its pre-release status and per-call-site
suppression requirement make mypy the lower-friction choice today.

A non-strict posture is deliberate: only `check_untyped_defs` is enabled, not
`strict` or `disallow_untyped_defs`. Strict mode is deferred to avoid a large
up-front annotation burden on an as-yet-unannotated codebase; it can be
tightened incrementally later.

## Consequences

- `[tool.mypy]` in `pyproject.toml` sets `files = ["src"]`, so `tests/` is not
  type-checked.
- `[[tool.mypy.overrides]]` sets `ignore_missing_imports = true` for `filters`
  and `filters.*`. This is broader than the `import-untyped` marker: it silences
  *all* import-resolution errors for those modules, so a genuinely wrong filters
  import path would go unflagged. Accepted as a false-negative trade-off; remove
  the override once phx-filters ships type information.
- mypy runs on every commit via `autohooks.plugins.mypy`, adding wall-clock time
  to the pre-commit gate.
- One real type error surfaced and fixed: a list annotation in [`build.py`][] and a
  re-annotated parameter in [`filters.py`][] (replaced with `cast`).
- `uv run mypy src/` added to the commands documented in [`AGENTS.md`][].

[`AGENTS.md`]: ../../AGENTS.md
[`autohooks-plugin-mypy`]: https://pypi.org/project/autohooks-plugin-mypy/
[`build.py`]: ../../src/paddock/docker/build.py
[`filters.py`]: ../../src/paddock/config/filters.py
[mypy]: https://github.com/python/mypy
[phx-filters]: https://github.com/todofixthis/filters
[ty]: https://github.com/astral-sh/ty
