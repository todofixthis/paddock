---
name: phx-filters
description: Use when writing or debugging phx-filters validation code in this project — covers filter composition, custom filters, FilterMapper, FilterRepeater, and the project's ordering conventions
---

# Working with phx-filters

This skill covers only the non-obvious aspects of phx-filters as used in this project. Refer to the library's own source (`.venv/lib/python3.14/site-packages/filters/`) for full API details.

## Filter composition with `|`

Chaining filters with `|` creates a `FilterChain`. The chain applies filters left-to-right; the output of each filter becomes the input of the next. This produces a `FilterChain` object, not a callable class — use it with `FilterRunner` or inside a `FilterMapper`, but do not subclass it.

```python
# Correct: chain used inside a FilterMapper
'image': f.Required | f.Unicode | f.NotEmpty
```

## When to use a custom `BaseFilter` subclass

Write a custom filter (subclass `filters.base.BaseFilter`, override `_apply`) when:
- The logic involves both validation **and** transformation that will be reused in multiple places
- The transformation cannot be expressed as a simple `FilterChain`

The `Volume` and `Agent` filters in `src/paddock/config/filters.py` are the reference examples.

Custom filters are **not** for one-off validation — use a `FilterChain` instead.

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
`FilterMapper` automatically, so no `f.Optional(None)` prefix is needed:
```python
'build': _build_schema
```

## `f.FilterRepeater`

Applies a filter to every **value** in a mapping (dict). Keys are left unchanged.

```python
# Apply Volume filter to each value in the volumes dict
'volumes': f.Type(dict) | f.FilterRepeater(Volume) | f.Optional({})
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
