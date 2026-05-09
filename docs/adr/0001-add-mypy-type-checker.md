---
status: Accepted
date: 2026-05-09
tags: [tooling, type-checking, pre-commit, autohooks]
summary: Use mypy for static type checking, integrated via autohooks-plugin-mypy.
---

# 0001: Add mypy as Type Checker

## Context

The project has no static type checking. It targets Python 3.12+ and uses autohooks
for pre-commit quality gates (black, ruff, pytest). Introducing type checking will
catch errors earlier and improve confidence when modifying the codebase.

The `phx-filters` library has no `py.typed` marker or stubs, so any type checker
will report `import-untyped` (or equivalent) errors for its imports unless
suppressed at the module level.

## Options

### Option 1: Do nothing

Leave type checking to manual inspection and tests alone.

**Pros:** No setup cost; no false-positive noise.
**Cons:** Type errors reach review or runtime instead of pre-commit; no
type-grounded IDE feedback.
**Risks:** Regressions in type correctness are silent.

### Option 2: Add mypy (Accepted)

Add `mypy` and `autohooks-plugin-mypy` as dev dependencies. Configure a
`[[tool.mypy.overrides]]` section to suppress `import-untyped` for the
`filters` package globally. Enable `check_untyped_defs` so that unannotated
methods (e.g. `_apply` overrides) are still checked.

**Pros:** Battle-tested; `autohooks-plugin-mypy` is published on PyPI (no
custom plugin needed); `[[tool.mypy.overrides]]` suppresses the phx-filters
noise at the package level rather than at individual call sites.
**Cons:** Slower than newer checkers; second ecosystem alongside Astral
tooling (uv, ruff).
**Risks:** phx-filters gains types in a future release, making the override
redundant — low risk, easy to remove.

### Option 3: Add ty

Add the Astral `ty` type checker. No published autohooks plugin exists,
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
suppression requirement make mypy the lower-friction choice today. This
decision can be revisited once ty stabilises and ships an autohooks plugin.

## Consequences

- `mypy` and `autohooks-plugin-mypy` added to the `dev` dependency group.
- `[tool.mypy]` section in `pyproject.toml` sets `files = ["src"]` and
  `check_untyped_defs = true`.
- `[[tool.mypy.overrides]]` suppresses `import-untyped` for `filters` and
  `filters.*`; remove once phx-filters ships type information.
- One real type error surfaced and fixed: `build.py` list annotation and a
  re-annotated parameter in `filters.py` (replaced with `cast`).
- `uv run mypy src/` added to the commands documented in `AGENTS.md`.
