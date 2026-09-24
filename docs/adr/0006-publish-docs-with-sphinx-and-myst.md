---
status: Accepted
date: 2026-09-23
scope: [.autohooks/docs_build.py, .github/workflows/build.yml, .readthedocs.yaml, docs/api.rst, docs/conf.py, docs/index.rst, docs/usage/, pyproject.toml]
summary: Build the docs with Sphinx and myst-parser, writing user pages in Markdown (not RST, not MkDocs), checked strictly (-W) by a pre-commit hook, CI and ReadTheDocs.
revisit-when: myst-parser stops supporting the current Sphinx major; the docs stop being hosted on ReadTheDocs; a published page needs to cross-reference Python's own documentation, which intersphinx would provide.
---

# 0006: Publish Docs with Sphinx and MyST

## Context

paddock's user docs are Markdown pages under `docs/usage/`, read on GitHub, with no
built or published form and nothing checking that their links and anchors resolve.
`README.rst` links into them by GitHub URL.

[`todofixthis/filters`][filters], by the same maintainer, publishes its docs to
ReadTheDocs with Sphinx, the `sphinx_rtd_theme`, autodoc and napoleon for
Google-style docstrings, and a `docs_build` autohooks plugin that fails a commit on
any Sphinx warning ([filters ADR 012][]). Its docs are RST; paddock's are Markdown.

paddock has one extension point worth documenting from code: agents register through
the `paddock.agents` entry-point group by subclassing [`BaseAgent`][].

## Options

### Option 1: Do nothing

**Pros:** No new dependencies or hooks.
**Cons:** No published docs. A broken in-page anchor or a renamed page goes unnoticed
until a reader follows the link.

### Option 2: Sphinx with myst-parser, Markdown sources (Accepted)

Mirror the filters setup, adding [myst-parser][] so Sphinx reads the existing
Markdown. `myst_heading_anchors = 3` makes GitHub-style `#heading` links resolve.

**Pros:** Existing pages build unchanged, and still render on GitHub. autodoc and
napoleon document `BaseAgent` from its docstrings.
**Cons:** Adds MyST's dialect for anything Markdown lacks (directives, roles).
**Risks:** MyST and Sphinx release separately; a Sphinx major can outpace MyST
support.

### Option 3: Sphinx, converting the pages to RST

**Pros:** Identical to filters' toolchain, one dependency fewer.
**Cons:** Rewrites every page, and future pages must be RST, which diverges from the
Markdown the rest of `docs/` (ADRs, deferred features, plans) is written in.

### Option 4: MkDocs

**Pros:** Markdown-native.
**Cons:** A second docs toolchain across the maintainer's projects, and no autodoc
equivalent without a plugin (mkdocstrings).

## Decision

Option 2. It keeps filters' toolchain, so the conventions carry between the two
projects, without converting the Markdown every other file under `docs/` uses.

Three deliberate departures from filters:

- **CI builds with `-W`.** filters' CI job builds leniently and relies on the
  pre-commit hook for strictness. Here `--no-verify` or an editor commit would skip
  that hook, leaving ReadTheDocs, after merge, as the only strict check.
- **No intersphinx.** Nothing in the published pages cites Python's docs, and
  fetching its inventory makes every docs-affecting commit depend on the network.
- **`nitpicky` on.** Without it, an unresolved Python cross-reference renders as
  plain text and the build stays green.

Only `docs/usage/` and the API page are published. ADRs, deferred features and plans
are excluded in `docs/conf.py`: they're for contributors and coding agents and
stay on GitHub.

## Consequences

- The `docs` dependency group holds Sphinx, myst-parser and the theme; `dev`
  includes it so the pre-commit hook can build. CI and ReadTheDocs sync with
  `--no-default-groups --group docs`: the project, for autodoc, plus the docs
  tools. Dropping the project (`--only-group`) breaks autodoc.
- A commit staging `docs/*.md`, `docs/*.rst`, `docs/conf.py`, `pyproject.toml`
  or `src/*.py` runs a full (`-E`), strict Sphinx build. ADR-only commits pay for
  one too, since `docs/*.md` matches them.
- The hook builds the working tree, not the staged snapshot, so an unstaged fix
  can mask a broken staged page. CI builds the commit and catches it.
- Every type the API page's signatures name must itself be documented there,
  which is why the page carries `VolumeSpec`.
- Any page under `docs/usage/`, nested or not, is published through the index's
  `usage/**` glob toctree.
- The docs go live only once a maintainer creates the ReadTheDocs project for this
  repository.

[`BaseAgent`]: ../../src/paddock/agents/__init__.py
[filters]: https://github.com/todofixthis/filters
[filters ADR 012]: https://github.com/todofixthis/filters/blob/main/docs/adr/012-check-the-docs-build-in-the-pre-commit-hook.md
[myst-parser]: https://myst-parser.readthedocs.io/
