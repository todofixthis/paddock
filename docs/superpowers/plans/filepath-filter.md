# Plan: `Filepath` Filter and Tilde Expansion

**Status:** in progress
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

## Task 2 — Implement `Filepath` filter (TDD)

Write the tests first; the filter implementation must not exist until they are failing.

Tests use the `assert_filter_passes` and `assert_filter_errors` pytest fixtures provided by
phx-filters (injected automatically — no import needed). Tests follow the phx-filters naming
conventions: `test_pass_<sub_group>_<scenario>` / `test_fail_<sub_group>_<scenario>`.
`<sub_group>` is omitted when there is only one test in that group.

- [ ] **Step 1: Write failing tests**

  Add to `tests/config/test_filters.py`. Add `from pathlib import Path` and `import pytest` to
  the imports, and `Filepath` to the `from paddock.config.filters import` line.

  ```python
  # ---------------------------------------------------------------------------
  # Filepath
  # ---------------------------------------------------------------------------

  @pytest.fixture(autouse=True)
  def _filepath_set_home(monkeypatch, tmp_path):
      """Set HOME to tmp_path for every test in this file.

      autouse=True means this applies to all tests in test_filters.py, not
      just the Filepath section. That is intentional and harmless — no other
      filter in this file reads HOME — but if a future filter does, move this
      fixture to a conftest scoped to a Filepath-only subdirectory or convert
      it to an explicit fixture.
      """
      monkeypatch.setenv("HOME", str(tmp_path))


  def test_pass_none(assert_filter_passes):
      """None is always a pass-through."""
      assert_filter_passes(Filepath, None, None)


  # -- tilde expansion --------------------------------------------------------

  def test_pass_tilde_expansion_applied_tilde_only(assert_filter_passes, tmp_path):
      """Bare ~ expands to HOME."""
      assert_filter_passes(Filepath, "~", tmp_path.resolve())


  def test_pass_tilde_expansion_applied_tilde_slash(assert_filter_passes, tmp_path):
      """~/ expands to HOME."""
      assert_filter_passes(Filepath, "~/", tmp_path.resolve())


  def test_pass_tilde_expansion_applied_str(assert_filter_passes, tmp_path):
      """~/foo expands to HOME/foo (str input)."""
      target = tmp_path / "foo"
      target.mkdir()
      assert_filter_passes(Filepath, "~/foo", target.resolve())


  def test_pass_tilde_expansion_applied_path_tilde_only(assert_filter_passes, tmp_path):
      """Path("~") expands to HOME."""
      assert_filter_passes(Filepath, Path("~"), tmp_path.resolve())


  def test_pass_tilde_expansion_applied_path_with_segment(assert_filter_passes, tmp_path):
      """Path("~/foo") expands to HOME/foo."""
      target = tmp_path / "foo"
      target.mkdir()
      assert_filter_passes(Filepath, Path("~/foo"), target.resolve())


  def test_pass_tilde_expansion_not_applied_abs(assert_filter_passes, tmp_path):
      """An absolute path without a leading tilde is returned as a Path object."""
      target = tmp_path / "file.txt"
      target.write_text("")
      assert_filter_passes(Filepath, str(target), target.resolve())


  def test_pass_tilde_expansion_not_applied_tilde_in_middle(assert_filter_passes, tmp_path):
      """A tilde not at the start of a path is treated as a literal character."""
      tilde_dir = tmp_path / "~in"
      tilde_dir.mkdir()
      target = tilde_dir / "middle"
      target.write_text("")
      assert_filter_passes(Filepath, str(target), target.resolve())


  def test_pass_tilde_expansion_custom_home_dir(assert_filter_passes):
      """A custom home_dir overrides Path.home() for tilde expansion."""
      assert_filter_passes(
          Filepath(home_dir="/custom/home"),
          "~/project",
          Path("/custom/home/project"),
      )


  # -- wrong type -------------------------------------------------------------

  def test_fail_wrong_type(assert_filter_errors):
      """A value that is neither str nor Path is rejected."""
      assert_filter_errors(Filepath(home_dir="/h"), 42, [f.Type.CODE_WRONG_TYPE])


  # -- resolve ----------------------------------------------------------------

  def test_pass_resolve_dot_segment(assert_filter_passes, tmp_path):
      """resolve=True resolves '.' segments in paths."""
      target = tmp_path / "target.txt"
      target.write_text("")

      # Use an f-string so the '.' reaches the filter as a string — Path() would
      # normalise it away before the filter sees it.
      assert_filter_passes(
          Filepath(home_dir=tmp_path, resolve=True),
          f"{tmp_path}/./target.txt",
          target.resolve(),
      )


  def test_pass_resolve_dotdot_segment(assert_filter_passes, tmp_path):
      """resolve=True resolves '..' segments in paths."""
      subdir = tmp_path / "sub"
      subdir.mkdir()
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(
          Filepath(home_dir=tmp_path, resolve=True),
          str(subdir / ".." / "target.txt"),
          target.resolve(),
      )


  def test_pass_resolve_symlink(assert_filter_passes, tmp_path):
      """resolve=True follows symlinks to their real target."""
      target = tmp_path / "target.txt"
      target.write_text("")

      link = tmp_path / "link.txt"
      link.symlink_to(target)

      assert_filter_passes(
          Filepath(home_dir=tmp_path, resolve=True),
          link,
          target.resolve(),
      )


  def test_fail_resolve_broken_symlink(assert_filter_errors, tmp_path):
      """A broken symlink is invalid when must_exist is effective (default)."""
      link = tmp_path / "link.txt"
      link.symlink_to(tmp_path / "target.txt")

      assert_filter_errors(
          Filepath(home_dir=tmp_path, resolve=True),
          link,
          [Filepath.CODE_DOES_NOT_EXIST],
      )


  # -- resolve: behaviour when home_dir is not set ----------------------------

  def test_pass_resolve_default_home_dir_activates(assert_filter_passes, tmp_path):
      """When home_dir is not set, resolve is enabled automatically."""
      subdir = tmp_path / "sub"
      subdir.mkdir()
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(
          Filepath,
          "~/sub/../target.txt",
          target.resolve(),
      )


  def test_pass_resolve_false_skips_resolution(assert_filter_passes, tmp_path):
      """Explicit resolve=False returns the tilde-expanded Path without resolution."""
      subdir = tmp_path / "sub"
      subdir.mkdir()
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(
          Filepath(resolve=False),
          "~/sub/../target.txt",
          tmp_path / "sub" / ".." / "target.txt",
      )


  # -- resolve: behaviour when home_dir is set --------------------------------

  def test_pass_resolve_defaults_off_with_home_dir(assert_filter_passes, tmp_path):
      """When home_dir is set, resolve is disabled by default."""
      subdir = tmp_path / "sub"
      subdir.mkdir()

      assert_filter_passes(
          Filepath(home_dir=tmp_path),
          "~/sub/../target.txt",
          tmp_path / "sub" / ".." / "target.txt",
      )


  def test_pass_resolve_explicit_true_with_home_dir(assert_filter_passes, tmp_path):
      """Explicit resolve=True resolves paths even when home_dir is set."""
      subdir = tmp_path / "sub"
      subdir.mkdir()

      assert_filter_passes(
          Filepath(home_dir=tmp_path, resolve=True),
          "~/sub/../target.txt",
          (tmp_path / "target.txt").resolve(),
      )


  # -- must_exist -------------------------------------------------------------

  def test_pass_must_exist_explicit_true_valid(assert_filter_passes, tmp_path):
      """must_exist=True passes when the path exists."""
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(Filepath(home_dir=tmp_path, must_exist=True), target)


  def test_fail_must_exist_explicit_true_invalid(assert_filter_errors, tmp_path):
      """must_exist=True is invalid when the path does not exist."""
      assert_filter_errors(
          Filepath(home_dir=tmp_path, must_exist=True),
          tmp_path / "target.txt",
          [Filepath.CODE_DOES_NOT_EXIST],
      )


  def test_pass_must_exist_false_missing(assert_filter_passes, tmp_path):
      """must_exist=False skips the existence check."""
      assert_filter_passes(
          Filepath(home_dir=tmp_path, must_exist=False),
          "~/./target.txt",
          tmp_path / "target.txt",
      )


  def test_pass_must_exist_resolve_false_valid(assert_filter_passes, tmp_path):
      """must_exist=True with resolve=False: explicit .exists() check passes."""
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(
          Filepath(home_dir=tmp_path, must_exist=True, resolve=False),
          "~/./target.txt",
          tmp_path / "." / "target.txt",
      )


  def test_fail_must_exist_resolve_false_invalid(assert_filter_errors, tmp_path):
      """must_exist=True with resolve=False: .exists() check rejects a missing path."""
      assert_filter_errors(
          Filepath(home_dir=tmp_path, must_exist=True, resolve=False),
          "~/./target.txt",
          [Filepath.CODE_DOES_NOT_EXIST],
      )


  # -- must_exist: behaviour when home_dir is not set -------------------------

  def test_pass_must_exist_default_activates(assert_filter_passes, tmp_path):
      """When home_dir is not set, must_exist is enabled automatically."""
      target = tmp_path / "target.txt"
      target.write_text("")

      assert_filter_passes(Filepath, "~/target.txt", target.resolve())


  def test_fail_must_exist_default_activates_missing(assert_filter_errors, tmp_path):
      """When home_dir is not set, missing paths are rejected automatically."""
      assert_filter_errors(
          Filepath,
          "~/missing.txt",
          [Filepath.CODE_DOES_NOT_EXIST],
      )


  def test_pass_must_exist_false_overrides_default(assert_filter_passes, tmp_path):
      """Explicit must_exist=False bypasses the default existence check."""
      assert_filter_passes(
          Filepath(must_exist=False, resolve=False),
          "~/missing.txt",
          tmp_path / "missing.txt",
      )
  ```

  Run `uv run pytest tests/config/test_filters.py` — all new tests must **fail** (ImportError or
  NameError on `Filepath`).

- [ ] **Step 2: Implement `Filepath` in `src/paddock/config/filters.py`**

  Add `from pathlib import Path` at the top if not already present. Add after the `Volume` class:

  ```python
  class Filepath(BaseFilter):
      """Expands a tilde prefix and returns a ``Path``.

      Accepts ``str`` or ``Path`` input. Place after ``f.Unicode`` in a chain
      — this filter asserts the type without coercing it.

      The ``resolve`` and ``must_exist`` parameters default to ``None``, which
      activates them automatically when no custom ``home_dir`` is supplied (host
      paths). Providing a ``home_dir`` disables both by default, because
      container paths cannot be resolved or checked from the host.

      Args:
          home_dir:

              Home directory to substitute for ``~``. When ``None``,
              ``Path.home()`` is used at apply time.

          resolve:

              When ``True``, or when ``None`` and ``home_dir`` was not
              supplied, calls ``.resolve()`` on the resulting path. If the path
              fails to resolve, the value is invalid.

          must_exist:

              When ``True``, or when ``None`` and ``home_dir`` was not
              supplied, the path must exist. If ``resolve`` is also effective,
              this sets ``strict=True`` on ``.resolve()``; otherwise an
              explicit ``.exists()`` check is used.
      """

      CODE_DOES_NOT_EXIST = "does_not_exist"

      templates = {
          CODE_DOES_NOT_EXIST: "Path {value!r} does not exist.",
      }

      def __init__(
          self,
          home_dir: "str | Path | None" = None,
          resolve: "bool | None" = None,
          must_exist: "bool | None" = None,
      ):
          super().__init__()
          self._home_dir = Path(home_dir) if home_dir is not None else None
          self._should_resolve = resolve is True or (
              resolve is None and home_dir is None
          )
          self._must_exist = must_exist is True or (
              must_exist is None and home_dir is None
          )

      def _apply(self, value):
          value: "str | Path" = self._filter(value, f.Type((str, Path)))
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

          return path
  ```

- [ ] **Step 3: Run filter tests**

  ```bash
  uv run pytest tests/config/test_filters.py -v
  ```

  All tests (old and new) must pass.

- [ ] **Step 4: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 5: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 3 — Apply `Filepath` to schema

**Note on return type:** `Filepath` returns `Path` objects. After updating the schema, `build.dockerfile` and `build.context` will be `Path` objects in the cleaned config. Check `src/paddock/docker/build.py` for any code that assumes these values are strings (e.g. `.startswith()`, `str` concatenation) and update accordingly.

- [ ] **Step 1: Fix pre-existing filter chains in `src/paddock/config/schema.py`**

  The existing chains incorrectly place `f.Optional(None)` at the start. `None` passes through
  all filters automatically — `f.Optional` is only needed when the fallback is a non-`None` value,
  and must always go at the end of the chain. Fix the chains before adding `Filepath`:

  ```python
  _build_schema = f.FilterMapper(
      {
          "args": f.FilterRepeater(f.Unicode),
          "context": f.Unicode | Filepath,
          "dockerfile": f.Required | f.Unicode | f.NotEmpty | Filepath,
          "policy": f.Choice(BUILD_POLICIES),
      },
      allow_extra_keys=False,
  )

  _config_schema = f.FilterMapper(
      {
          "agent": f.Required | Agent,
          "build": _build_schema,
          "image": f.Required | f.Unicode | f.NotEmpty,
          "network": f.Unicode,
          "volumes": f.FilterRepeater(Volume),
      },
      allow_extra_keys=False,
  )
  ```

  Notes:
  - `f.Optional(None)` removed from all chains — redundant since `None` is a natural pass-through.
  - `volumes` previously used `f.Optional(dict)` (the type, not an instance) — this was a bug.
    The default is now supplied by `_apply_defaults` before schema validation, so no `f.Optional`
    is needed here at all. Confirm the existing test suite still passes before proceeding.

- [ ] **Step 2: Import `Filepath` in `src/paddock/config/schema.py`**

  ```python
  from paddock.config.filters import Agent, Filepath, Volume
  ```

- [ ] **Step 3: Check and update `src/paddock/docker/build.py`**

  Read `build.py` and identify any uses of `build_config["dockerfile"]` or
  `build_config["context"]` that assume a `str`. Update them to work with `Path` objects (e.g.
  wrap in `str()` before passing to shell commands, or use `Path` methods directly).

- [ ] **Step 4: Add schema tests**

  Add to `tests/config/test_schema.py`. All tests that exercise `Filepath` must create real paths
  in `tmp_path` because `Filepath()` checks existence by default.

  ```python
  def test_build_dockerfile_tilde_expanded(monkeypatch, tmp_path):
      """'~/Dockerfile' is expanded using Path.home()."""
      monkeypatch.setenv("HOME", str(tmp_path))
      dockerfile = tmp_path / "Dockerfile"
      dockerfile.write_text("")
      raw = {
          "agent": "claude",
          "build": {"dockerfile": "~/Dockerfile"},
          "image": "myimage",
          "network": None,
          "volumes": {},
      }
      result = f.FilterRunner(_config_schema, raw)
      assert result.is_valid()
      assert not str(result.cleaned_data["build"]["dockerfile"]).startswith("~")


  def test_build_context_tilde_expanded(monkeypatch, tmp_path):
      """A tilde in build.context is expanded and resolved."""
      monkeypatch.setenv("HOME", str(tmp_path))
      context_dir = tmp_path / "myproject"
      context_dir.mkdir()
      dockerfile = tmp_path / "Dockerfile"
      dockerfile.write_text("")
      raw = {
          "agent": "claude",
          "build": {"dockerfile": "~/Dockerfile", "context": "~/myproject"},
          "image": "myimage",
          "network": None,
          "volumes": {},
      }
      result = f.FilterRunner(_config_schema, raw)
      assert result.is_valid()
      assert not str(result.cleaned_data["build"]["context"]).startswith("~")


  def test_build_context_none_unchanged(tmp_path):
      """None context passes through the filepath filter unchanged."""
      dockerfile = tmp_path / "Dockerfile"
      dockerfile.write_text("")
      raw = {
          "agent": "claude",
          "build": {"dockerfile": str(dockerfile), "context": None},
          "image": "myimage",
          "network": None,
          "volumes": {},
      }
      result = f.FilterRunner(_config_schema, raw)
      assert result.is_valid()
      assert result.cleaned_data["build"]["context"] is None
  ```

- [ ] **Step 5: Run full test suite**

  ```bash
  uv run pytest
  ```

  All tests must pass. Confirm test count has grown from 66.

- [ ] **Step 6: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 7: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 4 — Env var validation schema

`config_from_env` currently maps raw PADDOCK_* strings into config structure with no per-value
validation or coercion. Env vars should go through the same filter chains as equivalent TOML
values (including `Filepath` for path vars), so that validation is consistent regardless of
config source.

The structure difference from TOML: env vars are flat (`PADDOCK_BUILD_DOCKERFILE`) where TOML is
nested (`build.dockerfile`). Validate the raw `env` dict against a flat-key schema before
`config_from_env` maps them.

- [ ] **Step 1: Add `_env_schema` to `src/paddock/config/schema.py`**

  The schema validates only the PADDOCK_* keys this project recognises. All keys are optional
  (`allow_missing_keys=True`); unrecognised keys are allowed (`allow_extra_keys=True`) because the
  process environment contains many non-paddock vars.

  ```python
  _env_schema = f.FilterMapper(
      {
          "PADDOCK_AGENT": Agent,
          "PADDOCK_BUILD_ARGS": f.Unicode,
          "PADDOCK_BUILD_CONTEXT": f.Unicode | Filepath,
          "PADDOCK_BUILD_DOCKERFILE": f.Unicode | Filepath,
          "PADDOCK_BUILD_POLICY": f.Choice(BUILD_POLICIES),
          "PADDOCK_CONFIG_FILE": f.Unicode | Filepath,
          "PADDOCK_IMAGE": f.Unicode | f.NotEmpty,
          "PADDOCK_NETWORK": f.Unicode,
      },
      allow_extra_keys=True,
      allow_missing_keys=True,
  )
  ```

  Export `_env_schema` alongside `_config_schema`.

- [ ] **Step 2: Apply `_env_schema` in `src/paddock/config/loader.py`**

  In `resolve()`, validate `env` against `_env_schema` before reading
  `PADDOCK_CONFIG_FILE` or calling `config_from_env`. Print errors to stderr and exit on failure,
  consistent with `ConfigSchema.validate()`.

  The validated env dict (from `runner.cleaned_data`) replaces the raw `env` dict for all
  subsequent lookups. Because `Filepath()` has already resolved and expanded paths in the validated
  dict, the inline `Path(...).expanduser()` calls for `PADDOCK_CONFIG_FILE` and `parsed.config_file`
  are replaced by direct `Path(validated_env["PADDOCK_CONFIG_FILE"])` — expansion is already done.

  `parsed.config_file` comes from the CLI, not env, so it still needs expansion. Apply a
  `FilterRunner(Filepath(), parsed.config_file)` for that value, or use `Path(parsed.config_file).expanduser()`.

  Import `_env_schema` in `loader.py`.

- [ ] **Step 3: Add env schema tests**

  Add to `tests/config/test_loader.py` (or a new `tests/config/test_env_schema.py` if that keeps
  things cleaner):

  ```python
  def test_env_schema_expands_tilde_in_config_file(monkeypatch, tmp_path):
      """PADDOCK_CONFIG_FILE with a leading tilde is expanded by the env schema."""
      monkeypatch.setenv("HOME", str(tmp_path))
      config_file = tmp_path / "extra.toml"
      config_file.write_text("")
      runner = f.FilterRunner(_env_schema, {"PADDOCK_CONFIG_FILE": "~/extra.toml"})
      assert runner.is_valid()
      assert runner.cleaned_data["PADDOCK_CONFIG_FILE"] == config_file.resolve()


  def test_env_schema_expands_tilde_in_dockerfile(monkeypatch, tmp_path):
      """PADDOCK_BUILD_DOCKERFILE with a leading tilde is expanded by the env schema."""
      monkeypatch.setenv("HOME", str(tmp_path))
      dockerfile = tmp_path / "Dockerfile"
      dockerfile.write_text("")
      runner = f.FilterRunner(
          _env_schema, {"PADDOCK_BUILD_DOCKERFILE": "~/Dockerfile"}
      )
      assert runner.is_valid()
      assert runner.cleaned_data["PADDOCK_BUILD_DOCKERFILE"] == dockerfile.resolve()


  def test_env_schema_rejects_invalid_policy():
      """PADDOCK_BUILD_POLICY with an unrecognised value is invalid."""
      runner = f.FilterRunner(_env_schema, {"PADDOCK_BUILD_POLICY": "never"})
      assert not runner.is_valid()


  def test_env_schema_ignores_non_paddock_vars():
      """Non-PADDOCK_* vars in the env are silently ignored."""
      runner = f.FilterRunner(_env_schema, {"PATH": "/usr/bin", "HOME": "/home/user"})
      assert runner.is_valid()
  ```

  Also add a test confirming that validated env values flow through to the resolved config
  (an integration test through `ConfigLoader.resolve()`). Verify the exact call signature
  against the implementation before writing — the sketch below assumes `resolve()` reads
  `os.environ` by default:

  ```python
  def test_loader_resolve_env_dockerfile_tilde_expanded(monkeypatch, tmp_path):
      """A tilde in PADDOCK_BUILD_DOCKERFILE is expanded through ConfigLoader.resolve()."""
      monkeypatch.setenv("HOME", str(tmp_path))
      dockerfile = tmp_path / "Dockerfile"
      dockerfile.write_text("")
      monkeypatch.setenv("PADDOCK_BUILD_DOCKERFILE", "~/Dockerfile")
      monkeypatch.setenv("PADDOCK_IMAGE", "myimage")
      monkeypatch.setenv("PADDOCK_AGENT", "claude")

      config = ConfigLoader().resolve()
      assert config["build"]["dockerfile"] == dockerfile.resolve()
  ```

- [ ] **Step 4: Run full test suite**

  ```bash
  uv run pytest
  ```

  All tests must pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 6: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 5 — Final checks and PR

- [ ] **Step 1: Full test suite across all Python versions**

  ```bash
  uv run tox -p
  ```

  All environments must pass.

- [ ] **Step 2: Lint**

  ```bash
  uv run ruff check
  ```

- [ ] **Step 3: Docs build**

  ```bash
  uv run make -C docs clean && uv run make -C docs html
  ```

  No Sphinx warnings or errors.

- [ ] **Step 4: Open PR to `develop`**

  Push the feature branch and open a PR targeting `develop`.

- [ ] **Step 5: Compress this task in the plan**

  Use the `compress-plan-task` skill.

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
