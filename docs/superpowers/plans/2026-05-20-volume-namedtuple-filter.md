# Volume NamedTuple Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `Volume(BaseFilter)` class with a `VolumeSpec` NamedTuple (the data type) and a `@filter_macro Volume` (the composed filter), so the filter chain produces structured values instead of opaque strings.

**Architecture:** `VolumeSpec` is a `typing.NamedTuple` with `container_path: str` and `mode: str`, plus a `__str__` that renders `"container_path:mode"` for use in Docker `-v` flags. `Volume` becomes a `@filter_macro` wrapping `f.Unicode | f.NotEmpty | f.Split(":", keys=["container_path", "mode"]) | f.NamedTuple(VolumeSpec, {...})`; `Filepath` is always applied to the container path (with `resolve=False, must_exist=False`) to ensure absolute paths. `VolumeMap._apply`, `get_volumes()`, `get_scratch_volumes()`, and `_volume_flag` are all updated to use `VolumeSpec`.

**Tech Stack:** Python `typing.NamedTuple`, `filters.macros.filter_macro`, `f.Split` (with `keys`), `f.NamedTuple`, `f.CaseFold`, `f.Choice`, `f.Optional`

---

## Design Notes

### Why `Split(keys=...)` instead of `Split(...) | Len(max=2)`

`f.Split(":", keys=["container_path", "mode"])` on a 1-part string (bare path) produces `{"container_path": "...", "mode": None}` — the missing `mode` key is `None`, handled by `f.Optional("ro")`. It also raises `too_long` when more than 2 parts are present. This makes `f.Len(max=2)` redundant.

Using `f.Len(2)` (exact-length) without `keys` would reject bare paths (1-part lists fail NamedTuple's length check). Using `keys` is the cleaner approach.

### `f.Len.CODE_TOO_LONG` as the error-code reference for `f.Split`

`f.Split(keys=...)` emits the string `"too_long"` when there are more parts than keys. `f.Len.CODE_TOO_LONG` happens to equal `"too_long"`, making it the most semantically appropriate constant to reference in tests. There is no formal shared constant between the two filters — this is a coincidence of naming — but the value is stable across phx-filters 3.x.

### `Filepath` always applied to container paths

`Filepath(home_dir=home_dir, resolve=False, must_exist=False)` is used unconditionally in the `container_path` sub-filter, even when `home_dir` is `None`. Docker expects absolute paths for volume references; always running through `Filepath` ensures that tilde expansion is applied (either against the supplied `home_dir`, or against `Path.home()` as a fallback), converting any relative-looking paths to absolute before they reach Docker. `resolve=False, must_exist=False` are passed explicitly so container paths (which do not exist on the host) are not checked.

### `_volume_flag` accepts only `VolumeSpec`

All volume mounts in the builder — workdir, agent volumes, config volumes, scratch volumes — are converged onto `VolumeSpec`. `get_volumes()` and `get_scratch_volumes()` in `BaseAgent` and concrete agents are updated accordingly. `_volume_flag` is tightened to `container_spec: VolumeSpec` (no `str` union). `VolumeSpec.__str__` renders the correct `"container_path:mode"` suffix for `-v` flag construction.

---

## File Map

| File | Change |
|---|---|
| `src/paddock/config/filters.py` | Add `VolumeSpec` NamedTuple; replace `Volume(BaseFilter)` with `@filter_macro Volume` (always using `Filepath`); update `VolumeMap` docstring and cast type |
| `src/paddock/agents/__init__.py` | Change `get_volumes()` return type to `dict[str, VolumeSpec]`; change `get_scratch_volumes()` return type to `dict[str, VolumeSpec]` |
| `src/paddock/agents/claude.py` | Return `VolumeSpec` from `get_volumes()` |
| `src/paddock/docker/builder.py` | Import `VolumeSpec`; tighten `_volume_flag` to `container_spec: VolumeSpec`; convert workdir mount to `VolumeSpec` |
| `tests/config/test_filters.py` | Rewrite Volume tests to assert `VolumeSpec` return values and updated error codes; import `VolumeSpec` |
| `tests/config/test_schema.py` | Update `test_valid_volumes` to compare against `VolumeSpec` instances; import `VolumeSpec` |
| `tests/docker/test_builder.py` | Update `test_config_volumes` and `test_scratch_volume` to pass `VolumeSpec` instances |

---

### Task 1: Rewrite Volume filter tests (TDD — write first, run to confirm failure) ✅

Rewrote the Volume and VolumeMap tests in `tests/config/test_filters.py` before touching the implementation. The four old `test_volume_*` functions (string assertions, `Volume.CODE_INVALID` reference) were replaced with eight new ones following phx-filters naming convention (`test_volume_pass_none` first, then pass/fail groups). All new tests assert `VolumeSpec(...)` return values; `test_volume_map_invalid_container_spec` now uses `f.Len.CODE_TOO_LONG`; home_dir and VolumeMap output tests updated to `VolumeSpec` instances. Confirmed red state: collection fails with `ImportError: cannot import name 'VolumeSpec'`.

---

### Task 2: Implement `VolumeSpec` and `Volume` filter macro ✅

Added `VolumeSpec(NamedTuple)` with `container_path: str`, `mode: str`, and `__str__` returning `f"{container_path}:{mode}"` to `src/paddock/config/filters.py`. Replaced `class Volume(BaseFilter)` with a `@filter_macro` function using the chain `f.Unicode | f.NotEmpty | f.Split(":", keys=["container_path", "mode"]) | f.NamedTuple(VolumeSpec, {...})`; `Filepath(home_dir=home_dir, resolve=False, must_exist=False)` is unconditionally applied to `container_path` (followed by `f.Unicode` to coerce the `Path` back to `str`), with mode using `f.CaseFold | f.Choice({"ro", "rw"}) | f.Optional("ro")`. Updated `VolumeMap` cast to `VolumeSpec | None` and docstring to `dict[str, VolumeSpec]`. All 17 volume filter tests pass; `test_valid_volumes` in `test_schema.py` fails as expected (addressed in Task 3); mypy clean.

---

### Task 3: Propagate `VolumeSpec` through agents and builder ✅

Updated `BaseAgent.get_volumes()` and `get_scratch_volumes(self, image: str)` return types to `dict[str, VolumeSpec]` in `src/paddock/agents/__init__.py` (first-party import separated from `class_registry` by a blank line). `ClaudeAgent.get_volumes()` now returns `{str(Path.home() / ".claude"): VolumeSpec("/root/.claude", "rw")}` and `ShellAgent.get_volumes()` carries the updated annotation. In `builder.py`, `_volume_flag` is tightened to `container_spec: VolumeSpec` and the workdir mount uses `VolumeSpec(str(self._workdir), "rw")`; `VolumeSpec.__str__` renders `container_path:mode` in the f-string. `test_valid_volumes` in `test_schema.py` updated to assert `VolumeSpec(...)` instances; `test_config_volumes` and `test_scratch_volume` in `test_builder.py` updated similarly (scratch assertion now checks `"/scratch:rw"` because `VolumeSpec.__str__` always appends the mode). The implementer added `dict[str, object]` annotations to config dicts in `test_builder.py` to satisfy mypy. 126 tests pass, mypy and ruff clean.

---

## Intentional Decisions

- **Pre-existing docstring gaps not fixed in this PR.** The quality reviewer flagged `DockerCommandBuilder.__init__` (no docstring) and `BaseAgent.get_command` ("Default command" on an `@abstractmethod`). Both are pre-existing issues predating this refactor. Fixing them is out of scope here.

- **`get_scratch_volumes(self, image: str)` keeps the `image` parameter.** The spec reviewer's Item 3 incorrectly described the signature as parameterless. The plan's Step 1 code block explicitly includes `image: str`, and the builder calls `self._agent.get_scratch_volumes(self._config["image"])`. The parameter is load-bearing — agents that need image-specific scratch volume names use it. The implementation is correct.

---

## Self-Review Checklist

- [ ] Does the plan header include a `**Worktree:**` field? *(N/A — no worktree created for this task)*
- [ ] Does every commit step remind the agent to run `git status` first?
- [ ] Does every task end with a compression step?
- [ ] Does the plan include an Intentional Decisions section?
- [ ] Spec coverage: are all requirements addressed?
- [ ] No placeholders (TBD, TODO, "add appropriate error handling", etc.)?
- [ ] Type consistency: do types and names match across tasks?
