# Plan: `Filepath` Filter and Tilde Expansion

**Status:** not started
**Worktree:** TBD — see Task 1, Step 1

## Background

Config values that accept file paths may contain `~` (tilde home-directory shorthand). Currently nothing expands the tilde, so a path like `~/projects/myapp/Dockerfile` would be passed verbatim to Docker and fail. We need a `Filepath` filter that expands `~` at the schema level, using the Unix philosophy (one job only — no type coercion).

The filter is always placed *after* `f.Required | f.Unicode` (or `f.Optional | f.Unicode`) in a chain; it asserts `Type((str, Path))` internally rather than coercing.

## Scope — where the filter applies

| Location | Key | Notes |
|---|---|---|
| `config/schema.py` | `build.dockerfile` | Required path |
| `config/schema.py` | `build.context` | Optional path |
| `config/loader.py:176` | `PADDOCK_CONFIG_FILE` env var | Expanded before `Path()` |
| `config/loader.py:179` | `--config-file` CLI arg | Expanded before `Path()` |

The loader paths (rows 3–4) are host-system paths that bypass the schema; tilde expansion is applied inline via `Path(x).expanduser()` rather than through the filter chain.

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

Accepts `str | Path` input — checked with `f.Type((str, Path))` (assert, not coerce). The input is stringified for tilde detection, then always returned as a `Path`.

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

    str_value = str(value)
    home = self._home_dir if self._home_dir is not None else Path.home()

    if str_value == "~":
        path = Path(home)
    elif str_value.startswith("~/"):
        path = Path(home) / str_value[2:]
    else:
        path = Path(value)

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

## Task 1 — Create worktree and feature branch

- [ ] **Step 1: Record worktree path**

  Run:
  ```bash
  git worktree add .worktrees/filepath-filter -b feature/filepath-filter origin/develop
  ```
  Then:
  ```bash
  cd .worktrees/filepath-filter && uv run autohooks activate --mode=pythonpath
  ```
  Update the `**Worktree:**` field in this plan's header with the path and branch name.

- [ ] **Step 2: Verify test baseline**

  Run `uv run pytest --collect-only -q` inside the worktree and note the test count (currently 66). Confirm it does not change before any code is written.

- [ ] **Step 3: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 2 — Implement `Filepath` filter (TDD)

Write the tests first; the filter implementation must not exist until they are failing.

Tests use the `assert_filter_passes` and `assert_filter_errors` pytest fixtures provided by
phx-filters (injected automatically — no import needed). Tests follow the phx-filters naming
conventions: `test_pass_<sub_group>_<scenario>` / `test_fail_<sub_group>_<scenario>`.
`<sub_group>` is omitted when there is only one test in that group.

- [ ] **Step 1: Write failing tests**

  Add to `tests/config/test_filters.py`. Add `from pathlib import Path` to the imports and
  `Filepath` to the `from paddock.config.filters import` line.

  ```python
  # ---------------------------------------------------------------------------
  # Filepath
  # ---------------------------------------------------------------------------

  def test_pass_none(assert_filter_passes):
      """None is always a pass-through."""
      assert_filter_passes(Filepath(home_dir="/h"), None, None)


  # -- tilde expansion: applied -----------------------------------------------

  @pytest.mark.parametrize(
      "value,expected",
      [
          ("~", Path("/home/testuser")),
          ("~/", Path("/home/testuser")),
          ("~/foo", Path("/home/testuser/foo")),
          (Path("~"), Path("/home/testuser")),
          (Path("~/foo"), Path("/home/testuser/foo")),
      ],
  )
  def test_pass_tilde_expansion_applied(assert_filter_passes, value, expected):
      """Tilde prefix is expanded using the provided home dir (Path or str input)."""
      assert_filter_passes(Filepath(home_dir="/home/testuser"), value, expected)


  # -- tilde expansion: not applied -------------------------------------------

  @pytest.mark.parametrize(
      "value",
      [
          "/abs/path/file",
          "relative/path",
          "/path/~in/middle",
      ],
  )
  def test_pass_tilde_expansion_not_applied(assert_filter_passes, value):
      """Paths without a leading tilde are returned as-is (as Path objects)."""
      assert_filter_passes(Filepath(home_dir="/h"), value, Path(value))


  # -- tilde expansion: custom home dir ---------------------------------------

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
      assert_filter_errors(Filepath(home_dir="/h"), 42, ["wrong_type"])


  # -- resolve: path normalisation (home_dir set → resolve=False by default) --

  @pytest.mark.parametrize(
      "make_input,make_expected",
      [
          pytest.param(
              lambda p: str(p / "." / "file.txt"),
              lambda p: (p / "file.txt").resolve(),
              id="dot",
          ),
          pytest.param(
              lambda p: str(p / "sub" / ".." / "file.txt"),
              lambda p: (p / "file.txt").resolve(),
              id="dotdot",
          ),
          pytest.param(
              lambda p: str(p / "link.txt"),
              lambda p: (p / "target.txt").resolve(),
              id="symlink",
          ),
      ],
  )
  def test_pass_resolve_normalises(
      tmp_path, assert_filter_passes, make_input, make_expected
  ):
      """resolve=True (default when home_dir is None) resolves dots and symlinks."""
      (tmp_path / "sub").mkdir()
      (tmp_path / "file.txt").write_text("")
      target = tmp_path / "target.txt"
      target.write_text("")
      (tmp_path / "link.txt").symlink_to(target)
      assert_filter_passes(
          Filepath(),
          make_input(tmp_path),
          make_expected(tmp_path),
      )


  def test_fail_resolve_broken_symlink(tmp_path, assert_filter_errors):
      """A broken symlink is invalid when must_exist is effective (default)."""
      link = tmp_path / "link.txt"
      link.symlink_to(tmp_path / "ghost.txt")
      assert_filter_errors(Filepath(), str(link), [Filepath.CODE_DOES_NOT_EXIST])


  # -- resolve: behaviour when home_dir is not set ----------------------------

  def test_pass_resolve_default_home_dir_activates(tmp_path, assert_filter_passes):
      """When home_dir is not set, resolve is enabled automatically."""
      target = tmp_path / "file.txt"
      target.write_text("")
      assert_filter_passes(
          Filepath(),
          str(tmp_path / "." / "file.txt"),
          target.resolve(),
      )


  def test_pass_resolve_tilde_default_home_dir(
      tmp_path, monkeypatch, assert_filter_passes
  ):
      """When home_dir is not set, '~' expands via Path.home() and the result is resolved."""
      monkeypatch.setenv("HOME", str(tmp_path))
      (tmp_path / "file.txt").write_text("")
      assert_filter_passes(
          Filepath(),
          "~/file.txt",
          (tmp_path / "file.txt").resolve(),
      )


  def test_pass_resolve_false_skips_resolution(tmp_path, assert_filter_passes):
      """Explicit resolve=False returns the tilde-expanded Path without resolution."""
      assert_filter_passes(
          Filepath(home_dir=str(tmp_path), resolve=False),
          "~/sub",
          Path(tmp_path) / "sub",
      )


  # -- must_exist -------------------------------------------------------------

  def test_pass_must_exist_default_valid(tmp_path, assert_filter_passes):
      """Default Filepath() passes when the path exists."""
      target = tmp_path / "real.txt"
      target.write_text("")
      assert_filter_passes(Filepath(), str(target), target.resolve())


  def test_fail_must_exist_default_invalid(tmp_path, assert_filter_errors):
      """Default Filepath() is invalid when the path does not exist."""
      assert_filter_errors(
          Filepath(),
          str(tmp_path / "ghost.txt"),
          [Filepath.CODE_DOES_NOT_EXIST],
      )


  def test_pass_must_exist_false_missing(tmp_path, assert_filter_passes):
      """must_exist=False skips the existence check; missing path still resolves."""
      missing = tmp_path / "ghost.txt"
      assert_filter_passes(Filepath(must_exist=False), str(missing), missing.resolve())


  def test_pass_must_exist_resolve_false_valid(tmp_path, assert_filter_passes):
      """must_exist=True with resolve=False: explicit .exists() check passes."""
      target = tmp_path / "real.txt"
      target.write_text("")
      assert_filter_passes(
          Filepath(home_dir=str(tmp_path), resolve=False, must_exist=True),
          "~/real.txt",
          Path(tmp_path) / "real.txt",
      )


  def test_fail_must_exist_resolve_false_invalid(tmp_path, assert_filter_errors):
      """must_exist=True with resolve=False: explicit .exists() check fails."""
      assert_filter_errors(
          Filepath(home_dir=str(tmp_path), resolve=False, must_exist=True),
          "~/ghost.txt",
          [Filepath.CODE_DOES_NOT_EXIST],
      )
  ```

  Also add `import pytest` to the imports at the top of the file.

  Run `uv run pytest tests/config/test_filters.py` — all new tests must **fail** (ImportError or
  NameError on `Filepath`).

- [ ] **Step 2: Implement `Filepath` in `src/paddock/config/filters.py`**

  Add `from pathlib import Path` at the top if not already present. Add after the `Volume` class
  (use the spec above verbatim, filling in the docstring):

  ```python
  class Filepath(BaseFilter):
      """Expands a tilde prefix and returns a ``Path``.

      Accepts ``str`` or ``Path`` input. Place after ``f.Required | f.Unicode``
      or ``f.Optional(None) | f.Unicode`` in a chain — this filter asserts the
      type without coercing it.

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

          str_value = str(value)
          home = self._home_dir if self._home_dir is not None else Path.home()

          if str_value == "~":
              path = Path(home)
          elif str_value.startswith("~/"):
              path = Path(home) / str_value[2:]
          else:
              path = Path(value)

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

  All tests (old and new) must pass. **Note:** if `test_fail_wrong_type` fails because the actual
  error code differs from `"wrong_type"`, inspect `f.Type.CODE_WRONG_TYPE` and correct the
  assertion.

- [ ] **Step 4: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 5: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 3 — Apply `Filepath` to schema

**Note on return type:** `Filepath` returns `Path` objects. After updating the schema, `build.dockerfile` and `build.context` will be `Path` objects in the cleaned config. Check `src/paddock/docker/build.py` for any code that assumes these values are strings (e.g. `.startswith()`, `str` concatenation) and update accordingly.

- [ ] **Step 1: Update `src/paddock/config/schema.py`**

  Import `Filepath`:
  ```python
  from paddock.config.filters import Agent, Filepath, Volume
  ```

  Update the build schema entries. The default `Filepath()` resolves and checks existence — appropriate for a Dockerfile and context dir that must be present at build time:
  ```python
  "context": f.Optional(None) | f.Unicode | Filepath(),
  "dockerfile": f.Required | f.Unicode | f.NotEmpty | Filepath(),
  ```

- [ ] **Step 2: Check and update `src/paddock/docker/build.py`**

  Read `build.py` and identify any uses of `build_config["dockerfile"]` or `build_config["context"]` that assume a `str`. Update them to work with `Path` objects (e.g. wrap in `str()` before passing to shell commands, or use `Path` methods directly).

- [ ] **Step 3: Add schema tests**

  Add to `tests/config/test_schema.py`. Because `Filepath()` checks existence by default, paths must be created in `tmp_path`:

  ```python
  def test_build_dockerfile_tilde_expanded_with_tilde(tmp_path, monkeypatch):
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


  def test_build_context_tilde_expanded(tmp_path, monkeypatch):
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


  def test_build_context_none_unchanged():
      """None context is not touched by the filepath filter."""
      raw = {
          "agent": "claude",
          "build": {"dockerfile": "/Dockerfile", "context": None},
          "image": "myimage",
          "network": None,
          "volumes": {},
      }
      result = f.FilterRunner(_config_schema, raw)
      assert result.cleaned_data["build"]["context"] is None
  ```

  **Important:** `test_build_context_none_unchanged` uses `/Dockerfile` which likely does not exist
  on the test host. If `must_exist` rejects it, change the schema entry to
  `Filepath(must_exist=False)` and update these notes accordingly — then evaluate whether the
  other schema tests need similar adjustment.

- [ ] **Step 4: Run full test suite**

  ```bash
  uv run pytest
  ```

  All tests must pass. Confirm test count has grown from 66.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 6: Compress this task in the plan**

  Use the `compress-plan-task` skill.

---

## Task 4 — Expand tildes in `ConfigLoader`

Loader paths (`PADDOCK_CONFIG_FILE`, `--config-file`) bypass the schema, so expansion is applied inline using `Path.expanduser()`.

- [ ] **Step 1: Update `src/paddock/config/loader.py`**

  Lines 175–179 currently:
  ```python
  if paddock_config_file := env.get("PADDOCK_CONFIG_FILE"):
      sources.append(self.load_extra_config(Path(paddock_config_file)))

  if parsed.config_file is not None:
      sources.append(self.load_extra_config(Path(parsed.config_file)))
  ```

  Change to:
  ```python
  if paddock_config_file := env.get("PADDOCK_CONFIG_FILE"):
      sources.append(self.load_extra_config(Path(paddock_config_file).expanduser()))

  if parsed.config_file is not None:
      sources.append(self.load_extra_config(Path(parsed.config_file).expanduser()))
  ```

- [ ] **Step 2: Add loader tests**

  Add to `tests/config/test_loader.py`:

  ```python
  def test_resolve_expands_tilde_in_paddock_config_file(tmp_path, monkeypatch):
      """PADDOCK_CONFIG_FILE containing a leading tilde is expanded and loaded."""
      monkeypatch.setenv("HOME", str(tmp_path))
      config_file = tmp_path / "extra.toml"
      config_file.write_text('[build]\ndockerfile = "/Dockerfile"\n')

      loader = ConfigLoader()
      sourced = loader.load_extra_config(Path("~/extra.toml").expanduser())
      assert "build" in sourced


  def test_resolve_expands_tilde_in_config_file_arg(tmp_path, monkeypatch):
      """--config-file with a leading tilde is expanded before loading."""
      monkeypatch.setenv("HOME", str(tmp_path))
      config_file = tmp_path / "alt.toml"
      config_file.write_text('[build]\ndockerfile = "/Dockerfile"\n')

      loader = ConfigLoader()
      result = loader.load_extra_config(Path("~/alt.toml").expanduser())
      assert "build" in result
  ```

- [ ] **Step 3: Run full test suite**

  ```bash
  uv run pytest
  ```

  All tests must pass.

- [ ] **Step 4: Commit**

  Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

- [ ] **Step 5: Compress this task in the plan**

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
- [ ] Is tilde expansion confirmed at both the schema layer and the loader layer?
- [ ] Are `resolve` and `must_exist` each tested for effective-True, explicit-False, and the interaction case (resolve=False + must_exist=True)?
- [ ] Does every test that uses `Filepath()` (default home) either use a real existing path or set `must_exist=False`?
- [ ] Is `Path` imported in `filters.py`?
- [ ] Is `Filepath` exported/imported wherever it is used?
- [ ] Has `docker/build.py` been checked for code that assumes `dockerfile`/`context` are strings?
- [ ] Does `Filepath` return a `Path` object (not `str`) in all code paths?
- [ ] Does `Filepath` accept both `str` and `Path` input (via `f.Type((str, Path))`)?
