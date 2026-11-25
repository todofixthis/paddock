---
name: phx-filters
description: Use when writing or debugging phx-filters validation code in this project, including reusing a chain or schema in several places or running one from several threads — covers filter composition, filter_macro, custom filters, FilterMapper, FilterRepeater, and the project's ordering conventions
---

# Working with phx-filters

This skill covers only the non-obvious aspects of phx-filters as used in this project. Refer to the library's own source (`.venv/lib/python3.14/site-packages/filters/`) for full API details.

## Filter composition with `|`

Chaining filters with `|` creates a `FilterChain`. The chain applies filters left-to-right; the output of each filter becomes the input of the next. This produces a `FilterChain` object, not a callable class — use it with `FilterRunner` or inside a `FilterMapper`, but do not subclass it.

```python
# Correct: chain used inside a FilterMapper
'image': f.Required | f.Unicode | f.NotEmpty
```

When adding a filter to a chain using its default arguments, the brackets can be omitted — the class and a no-arg instance are equivalent in this context:

```python
# These two lines are equivalent
f.Unicode | Filepath()
f.Unicode | Filepath

# Non-default args always require brackets
f.Unicode | Filepath(home_dir="...")
```

## Share a chain or schema as a `filter_macro`

Define a chain or schema as a filter macro wherever one instance of it would otherwise be held by more than one chain, schema or run. That includes two fields, two schemas, a schema plus a direct `FilterRunner` call, and one schema run from several threads. It also includes a module-level instance referenced only once, if that reference is in a macro body, a custom filter's `__init__` or any function called more than once. A filter instance built and used by exactly one run is fine. Where you can't tell, as in library or web code that may run on several threads, use a macro.

```python
from typing import Any

import filters as f
from filters.base import BaseFilter


@f.filter_macro
def Text(max_length: int | None = None) -> f.FilterChain[str]:
    # Annotated, or mypy reads `f.Unicode | f.Strip` as a union of types
    chain: f.FilterChain[str] = f.Unicode | f.Strip | f.NotEmpty
    return chain if max_length is None else chain | f.MaxLength(max_length)


@f.filter_macro
def PostSchema() -> BaseFilter[dict[str, Any]]:
    return f.FilterMapper(
        {
            "summary": Text(max_length=500),
            "tag": Text,
            "title": f.Required | Text(max_length=80),
        },
        allow_extra_keys=False,
    )


# Each FilterRunner gets its own schema, so this is safe from any thread
runner = f.FilterRunner(PostSchema, data)
```

- **A macro is a filter class.** Each place that uses it, bare or in `|`, builds a new chain, and `FilterRunner(PostSchema, data)` builds one per run.
- **Name a new macro like a filter class** (`Text`), as filters are named. Where existing code or the task already fixes the name, such as `create_post_schema`, keep it: casing doesn't change how a macro composes, and an alias only adds a second name.
- **Give every macro parameter a default.** The macro then composes bare like a filter class (`"tag": Text`), and a caller passes only what differs (`Text(max_length=80)`). Calling a macro builds a filter instance, so call it only inside a macro body, including a schema built there. A module-level schema holding a macro call is itself a shared instance. For a named variant, preset the macro instead: `ShortText = f.filter_macro(Text, max_length=80)` is another macro, and `f.filter_macro(f.MaxLength, 80)` presets a built-in filter the same way. mypy doesn't check a macro's arguments, so a misspelt keyword or a missing required argument raises `TypeError` only when the schema is built: test each schema by running it at least once.
- **Annotate the return type with the output type** (`-> f.FilterChain[str]`, `-> BaseFilter[dict[str, Any]]`). Without it, the macro's output types as `Any`. Annotate a chain assigned to a variable too, as `Text` does: mypy reads an unannotated `f.Unicode | f.Strip` as a union of the two classes, not a chain.
- **Build every filter inside the macro's body.** A macro that returns, nests or `|`-extends a module-level filter instance shares that instance on every call. Likewise, a custom filter's `__init__` stores a macro class or a new instance, never a module-level filter instance. Constants that aren't filters, such as a frozenset of choices or a compiled regex, can stay at module level.
- `f.filter_macro` and `filters.macros.filter_macro` are the same function.

An instance is unsafe to share because it holds per-run state: `parent`, `key`, its handler and its error flag. `|` copies a chain's list of filters but not the filters in it, and `FilterMapper`, `FilterRepeater` and a chain each hold the instance itself. So a shared instance:

- files its errors under another holder's key, even on one thread. Building a `FilterMapper` around it sets its key, and a plain chain never clears it.
- gives wrong valid-or-invalid verdicts when one module-level schema is run by `FilterRunner` from several threads at once.
- can be left sending its errors to a finished `FilterRunner`'s handler, after which `apply()` swallows errors instead of raising.

todofixthis/filters#175 tracks the fix in phx-filters.

## When to use a custom `BaseFilter` subclass

Write a custom filter (subclass `filters.base.BaseFilter`, override `_apply`) when:
- The logic involves both validation **and** transformation that will be reused in multiple places
- The transformation cannot be expressed as a simple `FilterChain`

The `Volume` and `Agent` filters in `src/paddock/config/filters.py` are the reference examples.

Custom filters are **not** for one-off validation — use a `FilterChain` instead.

## Writing a custom filter's `_apply`

**Keep `_apply()` pure.** It should contain only validation and transformation of
`value` — no I/O, no deferred (function-body) imports, no computing lookups (the set of
valid choices, a schema, a reflected field list) at call time. Resolve those dependencies
in `__init__` and store them on the instance; `_apply` then reads the stored attribute.
If resolving a dependency in `__init__` causes a circular import, fix the module
boundaries (see AGENTS.md → Imports) rather than deferring the import into `_apply`.

**Reuse built-in filters inside `_apply`.** Don't hand-roll a check a built-in already
does — delegate to `self._filter(value, ...)` and let the built-in record the error:

```python
# Instead of: if not isinstance(value, dict): return self._invalid_value(...)
value = cast(dict, self._filter(value, f.Type(dict)))
if self._has_errors:
    return None
```

A custom filter should add only the logic no built-in provides; everything else composes
from existing filters. This keeps each custom filter doing one thing well.

## Filter chain ordering convention

Apply filters in this order:
1. `f.Required` — if the field must be present (omit for optional fields)
2. Type check / coercion (e.g. `f.Unicode`, `f.Type(dict)`)
3. Content filters (e.g. `f.NotEmpty`, `f.Choice(...)`, custom filters)
4. `f.Optional(default)` — **at the end only, and only when the default is non-`None`**

`None` passes through every filter automatically (handled by `BaseFilter` before `_apply` is
called), so `f.Optional(None)` is always redundant. Only use `f.Optional` when you need to
substitute a specific non-`None` fallback, and place it at the end so the default bypasses
all preceding validation.

**Exception — `FilterMapper` with `f.Optional`:** the placement of `f.Optional(callable)`
relative to a `FilterMapper` determines whether the sub-schema is applied to the default
value:

```python
sub = f.FilterMapper({"x": f.Unicode, "y": f.Unicode}, allow_missing_keys=True)

# f.Optional(dict) BEFORE FilterMapper:
#   None → {} → FilterMapper applies sub-chains → {'x': None, 'y': None}
f.Optional(dict) | sub

# f.Optional(dict) AFTER FilterMapper:
#   None → FilterMapper passes None through → None → f.Optional(dict) → {}
sub | f.Optional(dict)
```

Put `f.Optional(callable)` *before* `FilterMapper` when you want the sub-schema to run
(e.g. to populate missing-key defaults). Put it *after* when you want a plain empty dict
with no sub-schema applied.

For `FilterRepeater`, ordering does not matter — both placements produce `{}` for `None`
input, since an empty dict has no values to repeat over. Prefer placing `f.Optional(dict)`
before `FilterRepeater` for consistency with the `FilterMapper` convention:

```python
'volumes': f.Optional(dict) | f.FilterRepeater(Volume)
```

`f.Optional(dict)` works because `f.Optional` calls its argument when it is callable,
producing `dict()` → `{}`.

## String values go through `f.Unicode`

Put `f.Unicode` in the chain of every free-form string value, including each entry of
a list of strings. It applies Unicode normalisation, strips unprintable characters and
normalises line endings, which keeps a config file portable between systems.

`f.Unicode` also coerces: `1` becomes `"1"`, `True` becomes `"1"`, `False` becomes
`"0"`, and a table becomes its `repr`. Where converting a non-string to a string is
not appropriate, put `f.Type(str)` in front of it, as `agent` and
`agents.<name>.extra_args` do; otherwise use it bare. `f.Type(str)` augments
`f.Unicode` and never replaces it.

```python
# The default
f.Unicode | f.NotEmpty
# Converting a non-string is not appropriate
f.Type(str) | f.Unicode | f.NotEmpty
# A list of strings whose entries must not be coerced; without f.Array a bare
# string would be split into characters
f.Array | f.FilterRepeater(f.Type(str) | f.Unicode)
```

A value that may be a string or something else (`agent` is a name or `False`) must
not have `f.Unicode` at the front of its chain, which would turn `False` into `"0"`.
Branch on type in a custom filter and filter the string branch only, as `Agent` does
in `src/paddock/config/filters.py`.

## `f.FilterMapper`

Validates a dict against a schema. Each key maps to a filter chain.

```python
schema = f.FilterMapper(
    {
        'image': f.Required | f.Unicode | f.NotEmpty,
        'network': f.Unicode,  # None passes through automatically; no f.Optional needed
    },
    allow_extra_keys=False,  # unknown keys are errors
)
runner = f.FilterRunner(schema, data)
```

Use `allow_extra_keys=False` in all project schemas so typos in config files are caught.

For optional nested dicts (e.g. `build`), pass the sub-schema directly — `None` passes through
`FilterMapper` automatically, so no `f.Optional(None)` prefix is needed. Make the sub-schema a
macro (see "Share a chain or schema as a `filter_macro`"):
```python
'build': BuildSchema
```

## `f.FilterRepeater`

Applies a filter to every item in a list, or every **value** in a mapping (dict). A mapping's keys are left unchanged.

```python
# Apply Volume filter to each value in the volumes dict
'volumes': f.Optional(dict) | f.FilterRepeater(Volume)
```

## `f.FilterRunner`

Runs a filter against a single value and holds the result.

```python
runner = f.FilterRunner(MyFilter, value)
if runner.is_valid():
    result = runner.cleaned_data  # safe to access only after is_valid()
else:
    print(runner.errors)
```

Never access `cleaned_data` without first checking `is_valid()` — it raises if validation failed.

## Testing custom filters

phx-filters ships a pytest plugin (`filters.pytest`) that is registered automatically — no
import or configuration required. Use it for all custom filter tests.

### Fixtures

```python
def test_my_filter_passes(assert_filter_passes):
    # Omit expected_output when the output equals the input.
    assert_filter_passes(MyFilter(), input_value)
    # Supply it when the filter transforms the value.
    assert_filter_passes(MyFilter(), input_value, expected_output)

def test_my_filter_fails(assert_filter_errors):
    assert_filter_errors(MyFilter(), input_value, ["error_code"])
```

`assert_filter_errors` accepts either a list (checks the `""` key) or a full `{key: [codes]}` dict.

Use `from filters.pytest import skip_value_check` when a simple equality check is not practical —
omit the expected value and add manual assertions instead.

### Naming convention

Follow the phx-filters convention for all custom filter tests:

- `test_pass_none` — **always the first test** for a custom filter; confirms `None` is a pass-through (handled by `BaseFilter` before `_apply` is called)
- `test_pass_<sub_group>_<scenario>` — passing cases grouped by behaviour
- `test_fail_<sub_group>_<scenario>` — failing cases grouped by behaviour
- Omit `<sub_group>` when there is only one test in that group (e.g. `test_fail_wrong_type`)

### Error code references

Always use constant refs when asserting error codes — never hard-code the string literal:

```python
# Correct
assert_filter_errors(MyFilter(), value, [MyFilter.CODE_INVALID])
assert_filter_errors(MyFilter(), value, [f.Type.CODE_WRONG_TYPE])

# Wrong — a bare string obscures which filter and code path produced the error
assert_filter_errors(MyFilter(), value, ["invalid"])
assert_filter_errors(MyFilter(), value, ["wrong_type"])
```

### Narrowing `self._filter` return types with `cast`

`self._filter` returns `Any`. Always `cast` the result to the expected success type,
then guard with `_has_errors`. In loops where failure doesn't stop iteration, include
`None` in the cast and guard with `is not None` instead.

```python
# Early-return pattern (most _apply methods)
value = cast(str, self._filter(value, f.Unicode))
if self._has_errors:
    return None

# Loop pattern (no early return per entry)
host = cast(Path | None, self._filter(raw, f.Unicode | Filepath(), sub_key=k))
if host is not None:
    result[str(host)] = ...
```

### Multi-type input with `f.Type`

To assert that a value is one of several types (without coercing), pass a tuple:

```python
value = self._filter(value, f.Type((str, Path)))
```

The error code is `f.Type.CODE_WRONG_TYPE` = `"wrong_type"`.

## API gotchas discovered in this project

- **`f.Datetime`** (not `f.DateTime`) — phx-filters uses `Datetime` (lowercase 't').
- **`AutoRegister` from `class_registry.base`** — moved out of the top-level namespace in phx-class-registry v5. `EntryPointClassRegistry` also moved to `class_registry.entry_points`. See `docs/adr/` for the decision not to use `AutoRegister` in this project.
- **`EntryPointClassRegistry` with `attr_name` warms eagerly** — passing `attr_name` to `EntryPointClassRegistry.__init__` triggers immediate entry-point loading, which causes a circular import if entry-point modules import from the same package that defines the registry. Omit `attr_name` for lazy loading.
