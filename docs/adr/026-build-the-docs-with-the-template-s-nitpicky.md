---
status: Accepted
date: 2026-11-26
scope: [docs/conf.py]
summary: "Keep the template's nitpicky = True in docs/conf.py, not a local opt-out; fix a warning about paddock's own object in its docs, never in nitpick_ignore, which lists only a third-party target no mapped inventory resolves and never the collections.abc.Mapping entry docs/conf.py carried under ADR 023."
revisit-when: The template drops nitpicky; nitpick_ignore grows beyond a few entries; an unresolved cross-reference reaches the published docs despite nitpicky.
---

# 026: Build the Docs with the Template's Nitpicky

## Context

[ADR 025][] took cookiecutter-py's `docs/conf.py` whole when the template had
no `nitpicky`, and set three conditions on the template's answer: "the
template's docs/conf.py gains nitpicky", "cookiecutter-py declines nitpicky"
and "an unresolved cross-reference reaches the published docs", which waited
on `nitpicky` too. Template 1.7.0 answers ([cookiecutter-py ADR 024][]):
`docs/conf.py` sets `nitpicky = True` beside an empty `nitpick_ignore`, which
belongs to the project, as does `intersphinx_mapping`. Paddock took it in
[#79][]. Its strict build passes on that with only Python's inventory mapped.

## Options

### Option 1: Do nothing (Accepted)

Keep the template's lines as they arrived.

**Cons:** a change that adds an unresolved target fails the build until it
documents the target or adds an ignore entry.

### Option 2: Restore the ignore list kept under ADR 023

Under [ADR 023][], `docs/conf.py` ignored
`("py:class", "collections.abc.Mapping")` because it mapped no inventory.

**Cons:** Python's inventory now resolves that target, so the entry ignores
nothing until it hides a reference that genuinely breaks, and it is a line
paddock keeps through template-update conflicts.

### Option 3: Opt out locally

Set `nitpicky = False` in paddock's `conf.py`.

**Cons:** an unresolved cross-reference renders as plain text and the build
stays green, which ADR 023 turned `nitpicky` on to prevent. It diverges from
a template decision, which [ADR 024][] requires its own ADR for.

## Decision

Option 1. Nothing paddock publishes needs an ignore today, so the template's
setting costs paddock nothing until a warning appears, and that warning is
the defect the setting exists to catch.

## Consequences

- A warning about paddock's own object is fixed in its docs, as the comment
  above `nitpicky` in `docs/conf.py` says; only a third-party target no
  mapped inventory resolves earns a `nitpick_ignore` entry, added in the
  change that introduces it.
- Mapping a dependency's inventory adds one more inventory every
  docs-affecting build fetches over the network, as it already fetches
  Python's.

[#79]: https://github.com/todofixthis/paddock/pull/79
[ADR 023]: 023-write-the-user-docs-in-restructuredtext.md
[ADR 024]: 024-defer-to-cookiecutter-py-s-template-decisions.md
[ADR 025]: 025-publish-rst-user-docs-landing-on-the-readme.md
[cookiecutter-py ADR 024]: https://github.com/todofixthis/cookiecutter-py/blob/1.7.0/docs/adr/024-fail-generated-docs-builds-on-unresolved-cross-references.md
