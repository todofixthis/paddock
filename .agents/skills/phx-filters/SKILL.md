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
4. `f.Optional(default)` — **at the end only**, so the default bypasses all validation above

The `f.Optional(default)` at the end means: "if the value is missing/None after all other filters, substitute this default." Placing it at the start would skip all validation for the field.

## `f.FilterMapper`

Validates a dict against a schema. Each key maps to a filter chain.

```python
schema = f.FilterMapper(
    {
        'image': f.Required | f.Unicode | f.NotEmpty,
        'network': f.Optional(None),
    },
    allow_extra_keys=False,  # unknown keys are errors
)
runner = f.FilterRunner(schema, data)
```

Use `allow_extra_keys=False` in all project schemas so typos in config files are caught.

For optional nested dicts (e.g. `build`), the pattern is:
```python
'build': f.Optional(None) | f.Type(dict) | _build_schema
```
`f.Optional(None)` short-circuits and returns `None` when the value is absent; `_build_schema` only runs when a real dict is present.

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

## API gotchas discovered in this project

- **`f.Datetime`** (not `f.DateTime`) — phx-filters uses `Datetime` (lowercase 't').
- **`AutoRegister` from `class_registry.base`** — moved out of the top-level namespace in phx-class-registry v5. `EntryPointClassRegistry` also moved to `class_registry.entry_points`. See `docs/adr/` for the decision not to use `AutoRegister` in this project.
- **`EntryPointClassRegistry` with `attr_name` warms eagerly** — passing `attr_name` to `EntryPointClassRegistry.__init__` triggers immediate entry-point loading, which causes a circular import if entry-point modules import from the same package that defines the registry. Omit `attr_name` for lazy loading.
