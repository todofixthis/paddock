---
paths:
  - "docs/**/*.rst"
---

# Admonitions in docs

Use an admonition only for an aside readers must spot before they act: one whose miss
costs them a run that fails or misbehaves in a way they would struggle to trace back, a
risk to their data or security, or behaviour confined to one environment that would
leave a reader there hunting for the cause. A harmless quirk (an empty variable being
ignored), an optional feature and a shortcut all stay prose. Admonitions lose their pull
when every section has one, so give a section (the content under its nearest heading) at
most one; where two qualify, keep the higher-consequence one as the admonition and write
the other as prose.

Pick the type by consequence, taking the first that fits:

- `caution`: a risk to the reader's data or security.
- `warning`: the obvious approach breaks a run or behaves wrongly.
- `note`: the environment-specific case: paddock behaves differently in one setup,
  surprising a reader there and no one else.

Don't use any other admonition type.

Start the admonition with a bold line naming the case, so readers can judge from it
alone whether the admonition applies to them:

```rst
.. warning::

   **The build applies to whichever** ``image`` **the run ends up with**

   With ``build.dockerfile`` in your user file, a per-project ``image`` …
```

RST can't nest inline markup, so a code span in that line sits between bold runs, as
above, not inside one; a title that is all code stays an unbolded literal.
