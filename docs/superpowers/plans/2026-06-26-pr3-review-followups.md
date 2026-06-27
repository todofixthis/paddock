# PR #3 Review Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the larger architectural items from the PR #3 review so config-source responsibilities, the allowlist mechanism, and the `.paddock` lifecycle each sit behind sharp, registry-driven boundaries.

**Architecture:** The config layer is a `SortedClassRegistry` of `ConfigSource` subclasses. This plan (a) makes a plain-data field declaration the single source of truth for the config shape (removing reflection into `filters` private internals), (b) lets each source own both its instance config and its meta (`[config]`) via a structured `load()` result, (c) moves allowlist defaults onto the source classes so the orchestrator holds no per-source constant, (d) decomposes the loader's `resolve()` into phase methods, and (e) turns `ProjectDirManager` into a context manager raising an environment-specific error.

**Tech Stack:** Python 3.14, `filters` (phx-filters), `class_registry` (phx-class-registry), pytest with the `filters.pytest` plugin, mypy, ruff, autohooks.

**Worktree:** `.worktrees/project-config-security` (branch: `feature/project-config-security`)

## Global Constraints

- NZ English spelling; "Initialises" not "Initializes". Te Reo Māori where natural.
- All non-test implementation is class-based; tests are flat functions.
- Docstrings: Google/Napoleon (`Args:`/`Returns:`/`Note:`), ≤ 80 chars/line, blank line before lists in `Args:`, escaped backslashes.
- Comments on the line **preceding** the code; **no divider/banner comments**.
- Custom-filter tests follow the phx-filters convention: `test_pass_none` first; assert error codes via constant refs (`f.Type.CODE_WRONG_TYPE`), never string literals.
- Commit only via `uv run git commit` (autohooks). Never bare `git commit`.
- Imports: no function-body imports as a cycle workaround — extract the shared symbol into a third module instead.
- After each task: `uv run pytest` (expect ≥ 214 passing, count only grows), `uv run mypy src/` clean, `uv run ruff check` clean.
- `uv run pytest --collect-only -q` at start = **214 tests**; confirm the count only increases.

---

## File Map

- `src/paddock/config/fields.py` — **new.** Plain-data `CONFIG_FIELDS` declaration + `allowlist_directives()`. Pure (stdlib only); breaks the `filters.py ↔ schema.py` cycle.
- `src/paddock/config/schema.py` — source `allowlist_directives` from `fields`; delete `_STANDARD_FIELDS`/`_nested_fields`; `_allowlist_schema` and `config_meta_schema` drop their `f.Optional` defaults; `_ALLOWLIST_SOURCES` stays the static `{cli, env, project_toml}` (not registry-derived).
- `src/paddock/config/filters.py` — `AllowlistEntry` imports `allowlist_directives` at module level and resolves it in `__init__`.
- `src/paddock/config/sources/base.py` — `LoadResult` contract, `ALLOWLIST_DEFAULT`, removal of `sanitise`.
- `src/paddock/config/sources/*.py` — each source returns `LoadResult`; declares `ALLOWLIST_DEFAULT`; `user`/`project_overrides` populate meta.
- `src/paddock/config/context.py` — owns default user-config-path resolution.
- `src/paddock/config/allowlist.py` — built from registry class-defaults + explicit rules; default-deny fallback; `user` hard-wired enabled.
- `src/paddock/config/loader.py` — reads meta from sources (no re-parse); applies the allowlist generically; `resolve()` decomposed into phase methods; `_GATED_SOURCES` deleted.
- `src/paddock/config/project_dir.py` — context manager; raises `PaddockEnvironmentError`.
- `src/paddock/config/errors.py` — add `PaddockEnvironmentError`.
- `src/paddock/__main__.py` — `with ProjectDirManager(...)` lifecycle.
- `docs/adr/0002-*` → split into `0002` (registry sources) + `0003` (allowlist over denylist); renumber filenames; regenerate `INDEX.md`.

---

## Task 1: Declarative config fields + pure `AllowlistEntry`

Addresses review comments 3439473314 (`_filters` "no-go"), 3484383425 & 3484386614 (`_apply` purity / module-level import).

**Files:**
- Create: `src/paddock/config/fields.py`
- Create: `tests/config/test_fields.py`
- Modify: `src/paddock/config/schema.py`
- Modify: `src/paddock/config/filters.py:237-265` (`AllowlistEntry`)
- Test: `tests/config/test_filters.py` (existing `AllowlistEntry` tests), `tests/config/test_schema.py`

**Interfaces:**
- Produces: `paddock.config.fields.CONFIG_FIELDS: dict[str, tuple[str, ...]]`; `paddock.config.fields.allowlist_directives() -> list[str]`.
- Consumes (later tasks): `allowlist_directives()` from `fields`, not `schema`.

- [ ] **Step 1: Write the failing test for the field declaration**

Create `tests/config/test_fields.py`:

```python
from paddock.config.fields import CONFIG_FIELDS, allowlist_directives


def test_directives_include_top_level_keys():
    """Every top-level config key is a valid directive."""
    directives = set(allowlist_directives())
    assert {"agent", "build", "image", "network", "volumes"} <= directives


def test_directives_include_nested_build_keys():
    """Nested build keys are emitted dotted."""
    directives = set(allowlist_directives())
    assert {"build.args", "build.context", "build.dockerfile", "build.policy"} <= directives


def test_directives_match_declaration():
    """No directive exists outside the declaration (no private reflection)."""
    expected = {
        d
        for key, subs in CONFIG_FIELDS.items()
        for d in ([key] + [f"{key}.{s}" for s in subs])
    }
    assert set(allowlist_directives()) == expected
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/config/test_fields.py -q`
Expected: FAIL — `ModuleNotFoundError: paddock.config.fields`.

- [ ] **Step 3: Create `fields.py`**

```python
# Single source of truth for the standard config key structure. Each top-level
# key maps to its nested keys (empty tuple = leaf). Both the validation schema
# (schema.py) and the allowlist directive list are derived from this, so no
# code reflects into filters' private ``_filters`` internals.
CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "agent": (),
    "build": ("args", "context", "dockerfile", "policy"),
    "image": (),
    "network": (),
    "volumes": (),
}


def allowlist_directives() -> list[str]:
    """Return the valid dotted paths for ``[config.allowlist]`` list entries.

    Returns:
        Top-level keys (``image``, ``agent`` …) plus nested ones
        (``build.dockerfile`` …), derived from :data:`CONFIG_FIELDS`.
    """
    out: list[str] = []
    for key, subs in CONFIG_FIELDS.items():
        out.append(key)
        out.extend(f"{key}.{sub}" for sub in subs)
    return out
```

- [ ] **Step 4: Run the field test to verify it passes**

Run: `uv run pytest tests/config/test_fields.py -q`
Expected: PASS.

- [ ] **Step 5: Point `schema.py` at the declaration and delete the reflection**

In `schema.py`: remove `_STANDARD_FIELDS`, `_nested_fields`, and the local `allowlist_directives` (lines 72-75, 142-173). Re-export from `fields` for back-compat and add a sync guard. Replace the deleted `allowlist_directives` block with:

```python
from paddock.config.fields import CONFIG_FIELDS, allowlist_directives  # noqa: F401
```

Keep `_standard_fields`/`_build_schema` as-is (they still build the real filters). Add a co-location guard test rather than reflecting `_filters`.

- [ ] **Step 6: Add the schema/declaration sync guard test**

In `tests/config/test_schema.py` add:

```python
import filters as f

from paddock.config.fields import CONFIG_FIELDS, allowlist_directives
from paddock.config.schema import standard_config_schema


def test_every_directive_is_accepted_by_the_schema():
    """Each declared directive round-trips through the real schema."""
    for directive in allowlist_directives():
        parts = directive.split(".")
        config: dict = {}
        node = config
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = "x" if parts != ["volumes"] else {}
        runner = f.FilterRunner(standard_config_schema(merged=False), config)
        assert runner.is_valid(), (directive, runner.errors)


def test_unknown_nested_key_is_rejected():
    """A path outside the declaration fails schema validation."""
    runner = f.FilterRunner(
        standard_config_schema(merged=False), {"build": {"bogus": "x"}}
    )
    assert not runner.is_valid()
```

- [ ] **Step 7: Make `AllowlistEntry` pure**

In `filters.py`, add to the top-level imports:

```python
from paddock.config.fields import allowlist_directives
```

Replace the `AllowlistEntry` body (currently lazy-imports inside `_apply`) with:

```python
class AllowlistEntry(BaseFilter):
    """Validates a single ``[config.allowlist]`` entry.

    Accepts ``True``, ``False``, or a list of dotted-path strings naming keys
    in the standard config schema. The valid dotted paths come from
    :func:`paddock.config.fields.allowlist_directives`, resolved once in
    ``__init__`` so ``_apply`` stays pure.
    """

    CODE_INVALID = "invalid"
    templates = {
        CODE_INVALID: "Expected True, False, or a list of known config key paths.",
    }

    def __init__(self) -> None:
        super().__init__()
        self._directives = list(allowlist_directives())

    def _apply(self, value):
        if isinstance(value, bool):
            return value
        if isinstance(value, list):
            cleaned = self._filter(value, f.FilterRepeater(f.Choice(self._directives)))
            return cleaned if not self._has_errors else None
        return self._invalid_value(value, self.CODE_INVALID)
```

- [ ] **Step 8: Verify no import cycle and full suite green**

Run: `uv run python -c "import paddock.config.schema, paddock.config.filters, paddock.config.fields"`
Expected: no `ImportError`.
Run: `uv run pytest -q && uv run mypy src/ && uv run ruff check`
Expected: all pass; `schema.py` no longer references `_filters`.

- [ ] **Step 9: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Task 2: Source-owned meta via structured `load()` + ConfigContext owns the user path

Addresses review comments 3484513378 (orchestrator re-parses user TOML) and 3449028959 (`_default_user_config_path` belongs in `ConfigContext`). Fork decision: **split `load()` into instance + meta**.

**Files:**
- Modify: `src/paddock/config/sources/base.py`
- Modify: `src/paddock/config/sources/{user,project_overrides,env,cli,extra,project_toml}.py`
- Modify: `src/paddock/config/context.py`
- Modify: `src/paddock/config/schema.py:103-121` (`_allowlist_schema` stops auto-defaulting)
- Modify: `src/paddock/config/loader.py` (read meta from sources; drop `_extract_meta` re-parse)
- Test: `tests/config/sources/*`, `tests/config/test_loader.py`, `tests/config/test_context.py`

**Interfaces:**
- Produces: `paddock.config.sources.base.LoadResult` (dataclass) with `instance: f.FilterRunner` and `meta: dict`. `ConfigSource.load(context) -> LoadResult`. `ConfigContext.default_user_config_path() -> Path` (staticmethod). Sources that carry no meta return `meta = {}`.
- Consumes: `config_meta_schema` from `schema` (only `user`/`project_overrides`, to validate `[config]` as part of the file parse).
- Note: `meta` is a **plain dict, valid by construction** — it is only ever populated from an already-valid full runner (a malformed `[config]` invalidates the instance runner first), so it needs no separate validity check.

- [ ] **Step 1: Write the failing test for `LoadResult`**

In `tests/config/sources/test_user.py` add:

```python
from paddock.config.sources.base import LoadResult
from paddock.config.sources.user import UserConfigSource


def test_load_returns_loadresult_with_meta(tmp_path, monkeypatch):
    """User source surfaces [config] as validated meta, not stripped silently."""
    cfg = tmp_path / "config.toml"
    cfg.write_text('image = "u:1"\n[config.allowlist]\nproject_toml = true\n')
    from paddock.config.context import ConfigContext
    from paddock.cli import parse_args

    ctx = ConfigContext(
        parsed=parse_args([]),
        environ={},
        workdir=tmp_path,
        user_config_path=cfg,
    )
    result = UserConfigSource().load(ctx)
    assert isinstance(result, LoadResult)
    assert result.instance.cleaned_data == {"image": "u:1"}
    # Unset allowlist keys arrive as None from the mapper; only the explicit
    # key matters here.
    assert result.meta["allowlist"]["project_toml"] is True
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/config/sources/test_user.py::test_load_returns_loadresult_with_meta -q`
Expected: FAIL — `ImportError: LoadResult` / `load()` returns a `FilterRunner`.

- [ ] **Step 3: Define `LoadResult` and the new contract in `base.py`**

Replace the `load`/`sanitise` block. Add the dataclass and make `load` return it; **delete `sanitise`** (gating becomes generic — Task 3):

```python
from dataclasses import dataclass

@dataclass
class LoadResult:
    """A source's contribution: instance config plus optional meta.

    Attributes:
        instance: Runner whose ``cleaned_data`` conforms to the standard config
            shape on success; on a malformed file, the invalid source runner.
        meta: The validated ``[config]`` section as a plain dict (``{}`` for
            sources that carry no meta). Valid by construction — see the task
            Interfaces note.
    """

    instance: "f.FilterRunner"
    meta: dict
```

Change the abstract signature to `def load(self, context: ConfigContext) -> LoadResult:` and update its docstring. Remove the `sanitise` method entirely (the no-op base and the description). Keep `_annotate_source`. Sources with no meta return `meta={}` directly — no helper needed.

- [ ] **Step 4: Drop the auto-defaults from the meta schema**

In `schema.py`, two changes so that unset meta keys do **not** clobber the per-source class defaults the loader applies in Task 3.

`config_meta_schema` — replace `f.Optional(True)` on `project_dir_readonly` with `f.Type(bool)` so an unset value resolves to `None` (the loader supplies the `True` default, presence-aware), instead of always materialising `True` and masking the global setting:

```python
config_meta_schema = f.FilterMapper(
    {
        "allowlist": _allowlist_schema,
        # Not f.Optional(True): an unset value must stay None so the loader can
        # tell "unset" from an explicit False and fall back correctly. The
        # default True is applied in the loader, presence-aware.
        "project_dir_readonly": f.Type(bool),
    },
    allow_extra_keys=False,
    allow_missing_keys=True,
)
```

`_allowlist_schema` — drop the `f.Optional(False)` prefix:

```python
_allowlist_schema = f.FilterMapper(
    # No f.Optional default. NOTE: FilterMapper(allow_missing_keys=True) still
    # runs each filter for a *missing* key with None — AllowlistEntry passes
    # None through (BaseFilter short-circuits), so unset keys surface as
    # value None (not absent). The loader strips those None values before
    # overlaying explicit rules onto class defaults (see _extract_meta).
    {key: AllowlistEntry for key in _ALLOWLIST_SOURCES},
    allow_extra_keys=False,
    allow_missing_keys=True,
)
```

`_ALLOWLIST_SOURCES` stays the static `frozenset({"cli", "env", "project_toml"})` — **do not** derive it from the registry. Importing `paddock.config.schema` does not import `paddock.config.sources`, so at schema-construction time the registry is empty; a registry-derived `allow_extra_keys=False` mapper would reject every key. The static set also matches the intentional decision that `extra`/`project_overrides` are not user-restrictable.

- [ ] **Step 5: Update each source to return `LoadResult`**

`user.py` — add `config_meta_schema` to the `from paddock.config.schema import …` line; then parse once; instance = stripped standard fields; meta = validated `[config]` dict:

```python
def load(self, context: ConfigContext) -> LoadResult:
    schema = standard_config_schema(merged=False)
    path = context.user_config_path
    if not path.exists():
        return LoadResult(f.FilterRunner(schema, {}), {})

    full = f.FilterRunner(user_config_schema, path.read_text(encoding="utf-8"))
    if not full.is_valid():
        return LoadResult(full, {})

    cleaned = full.cleaned_data
    instance = {k: v for k, v in cleaned.items() if k not in self._META_SECTION_KEYS}
    return LoadResult(f.FilterRunner(schema, instance), cleaned.get("config") or {})
```

`project_overrides.py` — already imports `config_meta_schema`; split the extracted project entry into instance + its `config` meta:

```python
def load(self, context: ConfigContext) -> LoadResult:
    schema = standard_config_schema(merged=False)
    path = context.user_config_path
    if not path.exists():
        return LoadResult(f.FilterRunner(schema, {}), {})

    full_schema = standard_config_schema(
        extra_keys={"config": config_meta_schema}, merged=False
    )
    chain = f.TomlDecode | ExtractProject(project=context.project_key) | full_schema
    full = f.FilterRunner(chain, path.read_text(encoding="utf-8"))
    if not full.is_valid():
        return LoadResult(full, {})

    cleaned = full.cleaned_data
    instance = {k: v for k, v in cleaned.items() if k != "config"}
    return LoadResult(f.FilterRunner(schema, instance), cleaned.get("config") or {})
```

`env.py`, `cli.py`, `extra.py`, `project_toml.py` — wrap the existing instance runner and drop their `sanitise` override. Each `return f.FilterRunner(...)` becomes `return LoadResult(f.FilterRunner(...), {})`; delete the `sanitise` method and its now-unused `Allowlist` import from each.

- [ ] **Step 6: ConfigContext owns the default path**

In `context.py` add:

```python
@staticmethod
def default_user_config_path() -> Path:
    """Return ``~/.config/paddock/config.toml``, resolved at call time.

    Resolved per-call (not import time) so tests that redirect ``$HOME`` see
    the updated value.
    """
    return Path.home() / ".config" / "paddock" / "config.toml"
```

Delete `_default_user_config_path` from `user.py`. In `loader.py`, replace the import and its use with `ConfigContext.default_user_config_path()`.

- [ ] **Step 7: Loader reads meta from sources instead of re-parsing**

In `loader.py`, change Phase 1 to keep `LoadResult`s, and rewrite `_extract_meta` to read the (plain-dict) `results["user"].meta` and `results["project_overrides"].meta` — no `TomlDecode` re-parse, no raw file read. Two correctness points carried over from the review:

- **Strip `None` before overlaying** — unset allowlist keys arrive as `None` (the mapper runs `AllowlistEntry` for missing keys); a `None` must not overwrite a source's class default, and `is_enabled` would `len(None)` and crash.
- **Presence-aware `project_dir_readonly`** — `meta.get("project_dir_readonly")` is `None` when unset (Step 4 dropped `f.Optional(True)`), so fall through project-override → user → default `True` on `None`, not via `dict.get` defaults (the key is always present).

```python
def _extract_meta(self, results: dict[str, "LoadResult"]) -> tuple[Allowlist, bool]:
    """Build the Allowlist + project_dir_readonly from source-provided meta."""
    user_meta = results["user"].meta
    po_meta = results["project_overrides"].meta

    def _explicit(allowlist: dict | None) -> dict:
        # Keep only keys the user actually set; drop the None placeholders the
        # mapper injects for unset keys so class defaults survive the overlay.
        return {k: v for k, v in (allowlist or {}).items() if v is not None}

    allowlist_raw = {
        **_explicit(user_meta.get("allowlist")),
        **_explicit(po_meta.get("allowlist")),
    }

    readonly = po_meta.get("project_dir_readonly")
    if readonly is None:
        readonly = user_meta.get("project_dir_readonly")
    if readonly is None:
        readonly = True

    return Allowlist(allowlist_raw), bool(readonly)
```

This task keeps the **current** one-arg `Allowlist(raw)` (module-level `_DEFAULTS`); Task 3 relocates those defaults onto the source classes and switches this call to the two-arg form. `meta` is valid by construction (Task 2 Interfaces note), so the error-aggregation loop only checks `result.instance` validity.

Because Task 2 removes the per-source `sanitise` method, the loader's existing Phase-3c `cls().sanitise(runner, allowlist)` call must be replaced now with inline gating (still using the surviving `_GATED_SOURCES` and `Allowlist.filter`; Task 3 makes it generic):

```python
sanitised: dict[str, dict] = {}
for key, result in results.items():
    data = dict(result.instance.cleaned_data) if result.instance.is_valid() else {}
    sanitised[key] = (
        allowlist.filter(data, key) if key in _GATED_SOURCES else data
    )
```

- [ ] **Step 8: Update affected tests, then verify**

- Update `tests/config/sources/*` and `tests/config/test_loader.py` constructions that asserted a bare runner to use `.instance`; read `.meta` as a dict.
- Migrate source tests that called the now-deleted `.sanitise(...)` (`test_cli.py`, `test_env.py`, `test_project_toml.py`) — gating now happens in the loader, so move those assertions to `test_loader.py` or delete them.
- Add `tests/config/test_context.py::test_default_user_config_path_follows_home(monkeypatch, tmp_path)`.

Run: `uv run pytest -q && uv run mypy src/ && uv run ruff check`
Expected: all pass; `grep -n "TomlDecode" src/paddock/config/loader.py` returns nothing.

- [ ] **Step 9: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Task 3: Allowlist defaults on the source classes

Addresses 3449031528 & 3449038303 (per-class defaults, remove `sanitise`, default-deny, `user` always-enabled), 3484398857 (`_GATED_SOURCES` deleted), 3439468324 (consolidated "keys dropped" warning).

**Files:**
- Modify: `src/paddock/config/sources/base.py` (+`ALLOWLIST_DEFAULT`)
- Modify: `src/paddock/config/sources/*.py` (declare `ALLOWLIST_DEFAULT`)
- Modify: `src/paddock/config/allowlist.py` (two-arg constructor; default-deny; `user` enabled; `filter_with_report`)
- Modify: `src/paddock/config/loader.py` (build defaults from registry; generic gating; drop `_GATED_SOURCES`)
- Test: `tests/config/test_allowlist.py`, `tests/config/test_loader.py`

**Interfaces:**
- Produces: `ConfigSource.ALLOWLIST_DEFAULT: ClassVar[bool | list[str]]`. `Allowlist(defaults: dict, raw: dict)`. `Allowlist.filter_with_report(config, source_key) -> tuple[dict, list[str]]` (kept config + dropped top-level keys for the consolidated warning).
- Consumes: `source_registry` — **iterated in the loader** (which already imports it at module level) to build the defaults dict, so `allowlist.py` never imports `sources` and no function-body import is introduced.
- Note: `schema._ALLOWLIST_SOURCES` stays the static `{"cli", "env", "project_toml"}` — it is *not* registry-derived (see Task 2 Step 4 / Intentional Decisions). `extra`/`project_overrides` are trusted (`ALLOWLIST_DEFAULT = True`) but not user-restrictable.

- [ ] **Step 1: Write failing unit tests for the new constructor**

`Allowlist` is unit-tested in isolation with explicit `defaults`/`raw` dicts (no registry), so these tests stay fast and independent. In `tests/config/test_allowlist.py`:

```python
from paddock.config.allowlist import Allowlist

# Mirrors the class defaults the loader injects.
_DEFAULTS = {"cli": True, "env": True, "project_toml": False, "user": True}


def test_class_defaults_apply_when_unset():
    al = Allowlist(_DEFAULTS, {})
    assert al.is_enabled("env") is True
    assert al.is_enabled("project_toml") is False


def test_user_is_always_enabled_even_if_default_false():
    """The trusted user source is never gated, whatever the defaults say."""
    assert Allowlist({"user": False}, {}).is_enabled("user") is True


def test_unknown_source_defaults_denied():
    """A key in neither defaults nor raw is blocked (default-deny)."""
    assert Allowlist(_DEFAULTS, {}).is_enabled("mystery") is False


def test_explicit_rule_overrides_class_default():
    al = Allowlist(_DEFAULTS, {"project_toml": True})
    assert al.is_enabled("project_toml") is True


def test_filter_with_report_lists_dropped_keys():
    al = Allowlist(_DEFAULTS, {"project_toml": ["image"]})
    kept, dropped = al.filter_with_report(
        {"image": "x", "network": "n"}, "project_toml"
    )
    assert kept == {"image": "x"}
    assert dropped == ["network"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/config/test_allowlist.py -q`
Expected: FAIL — `Allowlist.__init__` takes one arg; `filter_with_report` undefined.

- [ ] **Step 3: Declare `ALLOWLIST_DEFAULT` on each source**

In `base.py` add `ALLOWLIST_DEFAULT: ClassVar[bool | list[str]] = False` (default-deny for any new source that forgets to set it). Each source sets it explicitly: `user`, `project_overrides`, `extra` → `True`; `env`, `cli` → `True`; `project_toml` → `False`.

- [ ] **Step 4: Rewrite `Allowlist` with the two-arg, default-deny constructor**

Rewrite `allowlist.py`: delete module-level `_DEFAULTS`. New `__init__(self, defaults: dict[str, bool | list[str]], raw: dict[str, Any]) -> None` stores `self._rules = {**defaults, **(raw or {})}`. Keep `allowlist.py` free of any `sources` import.

```python
def is_enabled(self, source_key: str) -> bool:
    """Whether a source may contribute. ``user`` is always enabled; an
    unknown key is blocked (default-deny)."""
    if source_key == "user":
        return True
    value = self._rules.get(source_key, False)
    if isinstance(value, bool):
        return value
    return len(value) > 0

def filter_with_report(self, config: dict, source_key: str) -> tuple[dict, list[str]]:
    """Return (kept, dropped) — the permitted config plus the sorted list of
    dropped top-level keys, for a single consolidated warning."""
    if not self.is_enabled(source_key):
        return {}, sorted(config)
    value = self._rules.get(source_key, True if source_key == "user" else False)
    if value is True:
        return dict(config), []
    kept = self._project(config, cast(list[str], value))
    dropped = sorted(set(config) - set(kept))
    return kept, dropped
```

Have `filter(self, config, source_key)` delegate: `return self.filter_with_report(config, source_key)[0]`. `_project`/`_copy_path` are unchanged.

- [ ] **Step 5: Loader builds defaults from the registry and gates generically**

In `loader.py`: delete `_GATED_SOURCES`. In `_extract_meta`, build the defaults dict from the registry (the loader already imports `source_registry` at module level) and pass both args:

```python
    defaults = {
        str(key): source_registry[key].ALLOWLIST_DEFAULT for key in source_registry
    }
    return Allowlist(defaults, allowlist_raw), bool(readonly)
```

Replace the per-source `sanitise` phase with a generic gate over every source, collecting a single consolidated warning per source that drops keys:

```python
kept, dropped = allowlist.filter_with_report(result.instance.cleaned_data, key)
sanitised[key] = kept
if dropped:
    logger.warning(
        "%s: dropped non-allowlisted keys %s — add them to "
        "[config.allowlist].%s to keep them",
        key, ", ".join(dropped), key,
    )
```

Keep the existing "source contributed but is disabled" warning, now driven by `is_enabled` (not `_GATED_SOURCES`).

- [ ] **Step 6: Migrate tests + verify**

- Update `tests/config/test_loader.py` warning assertions to the consolidated message.
- Any remaining single-arg `Allowlist({...})` or `.sanitise(...)` calls in `tests/config/` must be migrated (Task 2 deleted `sanitise`; this task changed the constructor).

Run: `uv run pytest -q && uv run mypy src/ && uv run ruff check`
Confirm `grep -rn "_GATED_SOURCES\|def sanitise\|_DEFAULTS\|from_registry" src/` is empty.

- [ ] **Step 7: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Task 4: Decompose `loader.resolve` + registry-driven instantiation

Addresses 3484499374 (no dividers; phase methods), 3484460709 & 3484471445 (let the registry instantiate), 3484493257 (filters#98 comment).

**Files:**
- Modify: `src/paddock/config/loader.py`
- Test: `tests/config/test_loader.py`

**Interfaces:**
- Produces: private `_load_sources`, `_validate`, `_warn_ignored`, `_sanitise`, `_merge` methods composed by `resolve`. No public-surface change (`resolve(parsed, workdir, environ) -> ResolvedConfig` unchanged).

- [ ] **Step 1: Confirm behaviour is pinned by existing tests**

Run: `uv run pytest tests/config/test_loader.py -q`
Expected: PASS (this is a pure refactor; the suite is the safety net).

- [ ] **Step 2: Replace `cls()` iteration with registry instantiation**

In `_load_sources`, iterate keys and let the registry instantiate (this also clears the `SortedClassRegistry.items()` deprecation the suite emits):

```python
# class_registry instantiates on subscription. Iterating keys + subscripting
# (rather than .items()/cls()) lets a future ClassRegistryInstanceCache slot in
# transparently. The str() coercion drops once todofixthis/class-registry#100
# ships a typed key.
results: dict[str, LoadResult] = {
    str(key): source_registry[key].load(context) for key in source_registry
}
```

- [ ] **Step 3: Extract each phase into a named method**

Split the current `resolve` body into `_load_sources(context)`, `_validate(results, allowlist)`, `_warn_ignored(results, allowlist)`, `_sanitise(results, allowlist)`, `_merge(sanitised)`. Remove **all** `# Phase N:` divider comments. `resolve` becomes a short composition:

```python
def resolve(self, parsed, workdir, environ) -> ResolvedConfig:
    context = self._build_context(parsed, workdir, environ)
    results = self._load_sources(context)
    allowlist, readonly = self._extract_meta(results)
    self._validate(results, allowlist)
    self._warn_ignored(results, allowlist)
    merged = self._merge(self._sanitise(results, allowlist))
    final = f.FilterRunner(standard_config_schema(merged=True), merged)
    if not final.is_valid():
        raise self._error_group([("final", final)])
    return ResolvedConfig(
        config=final.cleaned_data,
        project_toml_enabled=allowlist.is_enabled("project_toml"),
        project_dir_readonly=readonly,
    )
```

- [ ] **Step 4: Add the filters#98 forward-reference comment**

Where `dict(s_runner.cleaned_data)` coerces, add: `# dict() coercion drops once todofixthis/filters#98 types cleaned_data.`

- [ ] **Step 5: Verify the refactor is behaviour-preserving**

Run: `uv run pytest -q && uv run mypy src/ && uv run ruff check`
Expected: all pass; `grep -n "# Phase" src/paddock/config/loader.py` and `grep -n "\.items()" src/paddock/config/loader.py` both empty; no deprecation warning for `SortedClassRegistry.items()` in pytest output.

- [ ] **Step 6: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Task 5: `ProjectDirManager` as a context manager raising an environment error

Addresses 3484515776 (environment vs config error) and 3484520144 (context manager owns lifecycle).

**Files:**
- Modify: `src/paddock/config/errors.py`
- Modify: `src/paddock/config/project_dir.py`
- Modify: `src/paddock/__main__.py`
- Test: `tests/config/test_project_dir.py`, `tests/test_main.py`

**Interfaces:**
- Produces: `PaddockEnvironmentError(Exception)` in `errors.py`. `ProjectDirManager(workdir, *, readonly, enabled)` supporting `__enter__ -> tuple[str, VolumeSpec] | None` and `__exit__`.

- [ ] **Step 1: Write the failing tests**

In `tests/config/test_project_dir.py`:

```python
import pytest

from paddock.config.errors import PaddockEnvironmentError
from paddock.config.project_dir import ProjectDirManager


def test_not_a_directory_raises_environment_error(tmp_path):
    (tmp_path / ".paddock").write_text("oops")
    with pytest.raises(PaddockEnvironmentError):
        with ProjectDirManager(tmp_path, readonly=True, enabled=True):
            pass


def test_disabled_yields_none_and_no_dir(tmp_path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=False) as vol:
        assert vol is None
    assert not (tmp_path / ".paddock").exists()


def test_created_dir_removed_when_empty(tmp_path):
    with ProjectDirManager(tmp_path, readonly=True, enabled=True) as vol:
        assert vol is not None
    assert not (tmp_path / ".paddock").exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/config/test_project_dir.py -q`
Expected: FAIL — `PaddockEnvironmentError` undefined; `ProjectDirManager` is not a context manager.

- [ ] **Step 3: Add the environment error**

In `errors.py`:

```python
class PaddockEnvironmentError(Exception):
    """Raised when the host environment blocks paddock from running.

    Distinct from :class:`ConfigError`: the configuration is valid, but the
    filesystem/host state (e.g. ``.paddock`` already exists as a file) prevents
    paddock from proceeding.
    """
```

- [ ] **Step 4: Convert `ProjectDirManager` to a context manager**

```python
class ProjectDirManager:
    """Context manager for the ``.paddock`` directory lifecycle.

    On enter (when ``enabled``) ensures ``.paddock`` exists and yields its mount
    spec; on exit removes it only if paddock created it and it is still empty.
    When ``enabled`` is ``False`` it is an inert no-op yielding ``None``.
    """

    def __init__(self, workdir: Path, *, readonly: bool, enabled: bool) -> None:
        self._dir = workdir / PROJECT_DIR_NAME
        self._readonly = readonly
        self._enabled = enabled
        self._created = False

    def __enter__(self) -> tuple[str, VolumeSpec] | None:
        if not self._enabled:
            return None
        if self._dir.exists() and not self._dir.is_dir():
            raise PaddockEnvironmentError(
                f"{self._dir} exists but is not a directory; paddock cannot "
                "mount it as the project config directory"
            )
        if not self._dir.exists():
            self._dir.mkdir()
            self._created = True
        host_path = str(self._dir)
        mode = "ro" if self._readonly else "rw"
        return host_path, VolumeSpec(host_path, mode)

    def __exit__(self, *exc: object) -> None:
        if not self._created or not self._dir.exists():
            return
        if any(self._dir.iterdir()):
            logger.warning(
                "%s has contents after container exit — leaving in place "
                "for manual review",
                self._dir,
            )
            return
        self._dir.rmdir()
```

- [ ] **Step 5: Update `__main__.py` to use the `with` block**

Replace the `manager.prepare(...)` / try-finally-`cleanup` plumbing (lines 53-105) with a single `with`:

```python
try:
    with ProjectDirManager(
        workdir,
        readonly=resolved.project_dir_readonly,
        enabled=resolved.project_toml_enabled,
    ) as project_dir_volume:
        agent_key = "false" if config["agent"] is False else str(config["agent"])
        agent = agent_registry.get(agent_key)
        # … logging, maybe_build, DockerCommandBuilder.build, subprocess.run …
except PaddockEnvironmentError as e:
    print(str(e), file=sys.stderr)
    sys.exit(1)
```

Move the agent/logging/build/run block inside the `with`. `dry_run`'s `sys.exit(0)` inside the `with` still triggers `__exit__` (cleanup) via stack unwinding.

- [ ] **Step 6: Verify**

Run: `uv run pytest -q && uv run mypy src/ && uv run ruff check`
Expected: all pass.

- [ ] **Step 7: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Task 6: Split ADR 0002 into two and refresh the risks

Addresses 3439478483 (split registry vs allowlist decisions), 3439470838 (`AutoRegister` risk acknowledged), 3439473314 (the `_filters` risk is now resolved by Task 1).

**Files:**
- Modify/rename: `docs/adr/0002-project-config-security.md` → `0002-registry-driven-config-sources.md`
- Create: `docs/adr/0003-allowlist-over-denylist.md`
- Regenerate: `docs/adr/INDEX.md`

- [ ] **Step 1: Read the ADR skill and existing ADR**

Use the `writing-adrs` skill for format. Re-read `docs/adr/0002-project-config-security.md`.

- [ ] **Step 2: Rewrite 0002 as the registry-architecture decision**

Scope 0002 to: registry-driven `ConfigSource` architecture, `ConfigContext`, the source-owned `LoadResult` (instance + meta) boundary, two-mode `standard_config_schema`, and `ProjectDirManager` lifecycle. Record the declarative `CONFIG_FIELDS` single-source-of-truth (Task 1) under "Subsidiary decisions" and **remove** the `_filters`/`_STANDARD_FIELDS` risk bullet (no longer applicable). Soften the `AutoRegister` risk per the maintainer's note (same maintainer owns `class_registry`).

- [ ] **Step 3: Write 0003 as the allowlist-over-denylist decision**

New ADR covering: allowlist (opt-in) vs denylist, the threat model (untrusted checked-in change, not attacker-controlled shell), CI caveat, per-class `ALLOWLIST_DEFAULT` with default-deny fallback, `user` hard-wired enabled, and `project_toml` off by default as an application of the generic rule. Cross-link 0002 ⇄ 0003.

- [ ] **Step 4: Regenerate the index**

Run: `uv run python scripts/adr/generate_index.py` (confirm the script path), then verify `docs/adr/INDEX.md` lists 0001, 0002, 0003.

- [ ] **Step 5: Build the docs to confirm no Sphinx warnings**

Run: `uv run make -C docs clean && uv run make -C docs html`
Expected: build succeeds with no warnings (warnings are errors on RTD).

- [ ] **Step 6: Commit**

Run `git status` to catch any related unstaged or untracked files, then use the `creative-commits` skill.

---

## Intentional Decisions

*(Populated during review — reviewers must not re-raise these)*

- **`extra` and `project_overrides` stay trusted (`ALLOWLIST_DEFAULT = True`) and are NOT user-restrictable.** The valid `[config.allowlist]` keys remain the static `{cli, env, project_toml}` (`schema._ALLOWLIST_SOURCES`), not a registry-derived set. Reason (verified by review): `schema.py` is imported without `sources`, so a registry-derived key set would be empty at schema-construction time and reject every allowlist key. Full per-source uniformity is YAGNI anyway.
- **`Allowlist` does not import `sources`; the loader injects the defaults.** `Allowlist(defaults, raw)` is pure data; the loader (which already imports `source_registry` at module level) builds the `{key: ALLOWLIST_DEFAULT}` map. This honours the global "no function-body imports" rule — a `from_registry` classmethod on `Allowlist` would have needed a runtime `import sources` (cycle: `sources → base → allowlist → sources`).
- **Unset meta keys: dropped `f.Optional` defaults + strip `None` in the loader.** `FilterMapper(allow_missing_keys=True)` still runs each sub-filter for a *missing* key with `None`, so unset allowlist entries surface as `None` (not absent) and `project_dir_readonly` would mask the global if defaulted in-schema. The schema therefore uses bare `AllowlistEntry` / `f.Type(bool)` (no `f.Optional`), and the loader strips `None` before overlaying explicit rules onto class defaults and resolves `project_dir_readonly` presence-aware. (Verified blockers from review.)
- **`LoadResult.meta` is a plain dict, valid by construction.** A malformed `[config]` invalidates the *instance* runner first (the meta schema is embedded in the file-level schema), so meta never needs a separate validity check.
- **Fork decisions (confirmed with the maintainer):** #3 is solved declaratively in paddock (no phx-filters introspection API); #23 uses the `LoadResult` instance/meta split (not a separate `meta()` method).
- **Already-filed upstream issues are handled by forward-reference comments only:** phx-filters#92 (tilde), #93/#94 (`f.Item`/`ExtractProject` macro), #98 (typed `cleaned_data`), phx-class-registry#100 (typed keys). No upstream work is in scope for this branch.

## Self-Review

- **Spec coverage:** Every deferred review comment maps to a task — #3/#16/#17/#18 → Task 1; #23/#9 → Task 2; #11/#12/#13/#1/#18-const → Task 3; #22/#19/#20/#21 → Task 4; #25/#26 → Task 5; #4/#2 → Task 6. Done-already items (committed in 937575f) are excluded.
- **Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — each code step shows real code; each test step shows real assertions.
- **Type consistency:** `LoadResult(instance: f.FilterRunner, meta: dict)` defined in Task 2 is consumed by Tasks 3-4; `ALLOWLIST_DEFAULT` (per-source) and `Allowlist(defaults, raw)` / `filter_with_report` defined in Task 3 are used in Task 4's loader (defaults built from `source_registry` in `_extract_meta`); `PaddockEnvironmentError` defined in Task 5 is caught in `__main__`. `allowlist_directives` lives in `fields` from Task 1 onward. `meta` is read as a plain dict everywhere (never `.cleaned_data`).
