---
paths:
  - "docs/**/*.md"
---

# GitHub alerts in docs

Use a GitHub alert only for an aside readers must spot before they act: one whose miss
costs them a run that fails or misbehaves in a way they would struggle to trace back, a
risk to their data or security, or behaviour confined to one environment that would
leave a reader there hunting for the cause. A harmless quirk (an empty variable being
ignored), an optional feature and a shortcut all stay prose. Alerts lose their pull when
every section has one, so give a section (the content under its nearest heading) at
most one; where two qualify, keep the higher-consequence one as the alert and write the
other as prose.

Pick the type by consequence, taking the first that fits:

- `CAUTION`: a risk to the reader's data or security.
- `WARNING`: the obvious approach breaks a run or behaves wrongly.
- `NOTE`: the environment-specific case: paddock behaves differently in one setup,
  surprising a reader there and no one else.

Don't use `TIP` or `IMPORTANT`.

Start the alert with a bold line naming the case, so readers can judge from it alone
whether the alert applies to them:

```markdown
> [!WARNING]
> **A stale `[projects]` entry stops every run**
>
> paddock validates every `[projects]` entry on each run, not just the current one, …
```

Write alerts in this GitHub syntax, not MyST `{note}` directives, so they render on
GitHub as well as on ReadTheDocs. Sphinx renders them only through the `alert` entry in
`myst_enable_extensions` in `docs/conf.py`; without it, ReadTheDocs shows a literal
`[!NOTE]`.
