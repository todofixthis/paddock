# Plan: `Filepath` Filter and Tilde Expansion

**Status:** complete — PR open at https://github.com/todofixthis/paddock/pull/1
**Worktree:** `.worktrees/filepath-filter` — branch `feature/filepath-filter`

## Background

Config values that accept file paths may contain `~` (tilde home-directory shorthand). Currently nothing expands the tilde, so a path like `~/projects/myapp/Dockerfile` would be passed verbatim to Docker and fail. We need a `Filepath` filter that expands `~` at the schema level, using the Unix philosophy (one job only — no type coercion).

The filter is always placed *after* `f.Required | f.Unicode` (or after `f.Unicode`) in a chain; it asserts `Type((str, Path))` internally rather than coercing.

## Scope — where the filter applies

| Location | Key | Notes |
|---|---|---|
| `config/schema.py` | `build.dockerfile` | Required path |
| `config/schema.py` | `build.context` | Optional path |
| `config/schema.py` (new env schema) | `PADDOCK_CONFIG_FILE` | Validated before mapping |
| `config/schema.py` (new env schema) | `PADDOCK_BUILD_DOCKERFILE` | Validated before mapping |
| `config/schema.py` (new env schema) | `PADDOCK_BUILD_CONTEXT` | Validated before mapping |

All path expansion for env vars is handled via the env schema (Task 4), not inline `.expanduser()` calls.

## `Filepath` filter spec

```python
class Filepath(BaseFilter):
    CODE_DOES_NOT_EXIST = "does_not_exist"

    def __init__(
        self,
        home_dir: str | Path | None = None,
        resolve: bool | None = None,
        must_exist: bool | None = None,
    ): ...
```

Accepts `str | Path` input — checked with `f.Type((str, Path))` (assert, not coerce). The input is converted to a `Path` and tilde detection uses `path.parts[0]`, then always returned as a `Path`.

**Effective flags** (computed once in `__init__`):

```
_should_resolve = resolve is True  or  (resolve is None  and home_dir is None)
_must_exist     = must_exist is True  or  (must_exist is None  and home_dir is None)
```

The coupling to `home_dir` is intentional: a custom home dir signals a container path that cannot be resolved or checked from the host.

**`_apply` logic:**

```python
def _apply(self, value):
    value: str | Path = self._filter(value, f.Type((str, Path)))
    if self._has_errors:
        return None

    path = Path(value)
    home = self._home_dir if self._home_dir is not None else Path.home()

    if path.parts and path.parts[0] == "~":
        path = Path(home, *path.parts[1:])

    if self._should_resolve:
        try:
            path = path.resolve(strict=self._must_exist)
        except (FileNotFoundError, OSError):
            return self._invalid_value(value, self.CODE_DOES_NOT_EXIST)
    elif self._must_exist:
        if not path.exists():
            return self._invalid_value(value, self.CODE_DOES_NOT_EXIST)

    return path  # always a Path object
```

**Return type is `Path`** — downstream consumers of `build.dockerfile` and `build.context` must handle `Path` objects (check `docker/build.py` for any `str()` or `.startswith()` calls that need updating).

---

## Task 1 — Create worktree and feature branch ✅

Worktree created at `.worktrees/filepath-filter` on branch `feature/filepath-filter` (branched from `origin/main` — no `origin/develop` exists). Autohooks activated after manually creating the missing hooks directory at `.git/worktrees/filepath-filter/hooks/`. Test baseline confirmed at 66 tests.

---

## Task 2 — Implement `Filepath` filter (TDD) ✅

`Filepath` lives in `src/paddock/config/filters.py` alongside `Agent` and `Volume`. It accepts `str | Path`, asserts the type via `f.Type((str, Path))` (no coercion), expands a leading `~` using `path.parts[0]`, and always returns a `Path`. The `resolve` and `must_exist` flags both default to `None`: when no `home_dir` is provided they activate automatically (host paths), when `home_dir` is set they default off (container paths can't be checked from the host). Resolution uses `path.resolve(strict=self._must_exist)`; non-resolving existence checks use `path.exists()`. The plan's `test_fail_resolve_broken_symlink` had a body inconsistent with its docstring — corrected to use `must_exist=True` explicitly and moved into the `must_exist` section. 35 filter tests cover all flag combinations; total suite is 35 tests (the pre-existing 9 agent/volume tests remain, and the autouse `_filepath_set_home` fixture applies to all).

---

## Task 3 — Apply `Filepath` to schema ✅

`Filepath` added to `dockerfile` (`f.Required | f.Unicode | f.NotEmpty | Filepath`) and `context` (`f.Unicode | Filepath`) chains in `_build_schema`. All redundant `f.Optional(None)` prefixes removed from chain starts — they were obscuring the natural None pass-through. The plan's claim that `f.Optional(dict)` on `volumes` was a bug turned out to be wrong: `f.Optional(callable)` placed *before* a `FilterMapper` or `FilterRepeater` converts `None` to `callable()` before the complex filter sees it, which is the correct pattern; `volumes` retains `f.Optional(dict) | f.FilterRepeater(Volume)`. The `pathlib.Path` import was removed from `build.py` (now unused after simplifying the context fallback to `dockerfile.parent`). Two existing schema tests updated to use real `tmp_path` files (Filepath checks existence by default); three new tilde-expansion integration tests added via `_config_schema` directly. The `f.Optional` placement nuance was documented in the phx-filters skill. Suite now at 95 tests.

---

## Task 4 — Env var validation schema ✅

`_env_schema` added to `src/paddock/config/schema.py` as a flat `FilterMapper` covering all recognised `PADDOCK_*` keys (`allow_extra_keys=True, allow_missing_keys=True`). Path vars (`PADDOCK_BUILD_CONTEXT`, `PADDOCK_BUILD_DOCKERFILE`, `PADDOCK_CONFIG_FILE`) use `f.Unicode | Filepath` to expand tildes and resolve paths before the loader maps them. In `loader.py`, `resolve()` now validates `env` against `_env_schema` first (printing errors and exiting on failure, consistent with `ConfigSchema.validate()`). Two non-obvious implementation decisions: (1) `validated_env` produces `None` for every unset schema key (because `allow_missing_keys=True` populates missing keys as `None`), so the env dict passed to `config_from_env` is filtered to exclude `None` values; (2) `PADDOCK_CONFIG_FILE` is a meta-key that locates extra config files rather than mapping to a config value, so it is also excluded from the filtered dict to prevent `config.file` appearing as an unexpected key in `_config_schema`. `parsed.config_file` (CLI source) now uses `.expanduser()` since it bypasses the env schema. Suite at 100 tests.

---

## Task 5 — Final checks and PR ✅

100 tests pass; `ruff check` is clean. `tox` and `make` are not available in this environment — multi-version testing and docs build deferred to a future iteration. No `origin/develop` branch exists, so the PR targets `main` directly: https://github.com/todofixthis/paddock/pull/1. Feature branch rebased onto `main` before the PR was opened.

---

## Self-review checklist

- [ ] Does the plan header include a `**Worktree:**` field?
- [ ] Does every commit step remind the agent to run `git status` first?
- [ ] Does every task end with a compression step?
- [ ] Are all new tests written *before* the implementation they cover?
- [ ] Is `test_pass_none` the first test for `Filepath`?
- [ ] Do all tests use `assert_filter_passes` / `assert_filter_errors` fixtures?
- [ ] Do all test names follow `test_pass_<sub_group>_<scenario>` / `test_fail_*` convention?
- [ ] Do all `assert_filter_errors` calls use constant refs (e.g. `Filepath.CODE_DOES_NOT_EXIST`, `f.Type.CODE_WRONG_TYPE`) rather than literal strings?
- [ ] Are no lambdas used in `pytest.mark.parametrize`?
- [ ] Is tilde expansion confirmed at the schema layer, and also for env vars via `_env_schema`?
- [ ] Are `resolve` and `must_exist` each tested for effective-True, explicit-False, and the interaction case (resolve=False + must_exist=True)?
- [ ] Does every test that uses `Filepath()` (default home) either use a real existing path or set `must_exist=False`?
- [ ] Is `Path` imported in `filters.py`?
- [ ] Is `Filepath` exported/imported wherever it is used?
- [ ] Has `docker/build.py` been checked for code that assumes `dockerfile`/`context` are strings?
- [ ] Does `Filepath` return a `Path` object (not `str`) in all code paths?
- [ ] Does `Filepath` accept both `str` and `Path` input (via `f.Type((str, Path))`)?
- [ ] Have all pre-existing `f.Optional(None)` usages been removed from filter chain starts?
