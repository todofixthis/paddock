---
status: Accepted
date: 2026-10-02
scope: [.autohooks/docs_build.py, .github/workflows/build.yml, .readthedocs.yaml, README.rst, docs/api.rst, docs/conf.py, docs/index.rst, docs/usage/, pyproject.toml]
summary: Build the docs with Sphinx and myst-parser (Markdown user pages, not RST, not MkDocs), strictly (-W) in a pre-commit hook, CI and ReadTheDocs, with a landing page that includes README.rst rather than copying it, so the README must render on GitHub, PyPI and Sphinx alike.
revisit-when: myst-parser stops supporting the current Sphinx major; the docs stop being hosted on ReadTheDocs; a published page needs to cross-reference Python's own documentation, which intersphinx would provide; the README needs a construct GitHub, PyPI or Sphinx cannot render; the README stops being RST.
---

# 0008: Publish Docs with Sphinx and MyST, Landing on the README

## Context

[ADR 0006][] chose the docs toolchain and published only `docs/usage/` and an API page.
The landing page it produced carries a one-line tagline and the toctrees. Everything
else a user needs is in `README.rst` and nowhere on the docs site: the quick start,
config fields, CLI flags, the `--` grammar, agents and the Docker image. A reader
arriving at the docs site finds less than the README, which is also the PyPI long
description (`readme` in `pyproject.toml`).

This ADR restates ADR 0006 with the published set widened to the README, and supersedes
it. ADR 0006 weighed the toolchain, and its conclusions are restated in Decision; the
options below are about the landing page.

## Options

### Option 1: Do nothing

**Pros:** No change.
**Cons:** The docs site lacks the core reference, so readers bounce to GitHub or PyPI.

### Option 2: Include the README in the docs landing page (Accepted)

`docs/index.rst` is a single `.. include:: ../README.rst` followed by hidden toctrees,
which drive the sidebar without rendering on the page.

**Pros:** The include is plain docutils, so nothing needs regenerating or syncing.
**Cons:** The README must satisfy three renderers at once: GitHub, PyPI's
`readme_renderer`, and Sphinx under `-W` with `nitpicky`. The docs site's landing page
carries the README's link to the docs site itself.

### Option 3: Copy the README content into the docs

**Pros:** Each copy can be tuned to its medium.
**Cons:** Two copies of the same reference. Nothing checks that they agree, so they
drift.

### Option 4: Move the content into docs pages and slim the README to a pointer

**Pros:** One source, written in the docs' own Markdown.
**Cons:** The PyPI and GitHub pages become a link out, and the quick start is no longer
where most readers first land.

### Option 5: Generate the README from the docs

**Pros:** One source, with the docs site as the canonical form.
**Cons:** Needs a generator, plus a check that the committed README is current. It also
needs an RST or Markdown rendering acceptable to PyPI, which Sphinx doesn't produce
directly.

## Decision

The toolchain is ADR 0006's: Sphinx with myst-parser, the `sphinx_rtd_theme`, and
autodoc with napoleon for the `paddock.agents` extension point. It mirrors
[`todofixthis/filters`][filters], by the same maintainer, so conventions carry between
the two. User pages under `docs/usage/` stay Markdown: converting them to RST would
rewrite every page and diverge from the Markdown the rest of `docs/` uses, and MkDocs
would be a second toolchain across the maintainer's projects, with no autodoc equivalent
short of a plugin. A pre-commit hook, CI and ReadTheDocs (`fail_on_warning`) all build
strictly. Three departures from filters:

- **CI builds with `-W`**, since `--no-verify` or an editor commit skips the hook.
- **No intersphinx.** Nothing published cites Python's docs, and fetching its inventory
  makes every docs-affecting commit depend on the network.
- **`nitpicky` on**, since without it an unresolved Python cross-reference renders as
  plain text and the build stays green.

The published pages are the README as the landing page, everything under
`docs/usage/`, and the API page. ADRs, deferred features and plans stay excluded: they
are for contributors and coding agents, read on GitHub.

Option 2 for the landing page: it is the only option with one source and no generator
that keeps the full reference on GitHub and PyPI, where most readers first land. RST
comment markers could keep the README's link to the docs site off the docs site, by
including the README twice around them. That was tried and dropped: a link to the page
you're on is harmless, and a misplaced marker silently drops content from the docs site
while the build passes.

## Consequences

- The `docs` dependency group holds Sphinx, myst-parser and the theme; `dev` includes
  it so the pre-commit hook can build. CI and ReadTheDocs sync with
  `--no-default-groups --group docs`: the project, for autodoc, plus the docs tools.
  Dropping the project (`--only-group`) breaks autodoc.
- A commit staging `README.rst`, `docs/*.md`, `docs/*.rst`, `docs/conf.py`,
  `pyproject.toml` or `src/*.py` runs a full (`-E`), strict Sphinx build. ADR-only
  commits pay for one too, since `docs/*.md` matches them. The hook builds the working
  tree, not the staged snapshot, so an unstaged fix can mask a broken staged page; CI
  builds the commit and catches it.
- The README may use only constructs all three renderers accept. Sphinx accepts roles
  such as `:doc:` and `:ref:` that `readme_renderer` rejects, so the strict build can't
  vouch for the PyPI page. CI's `docs` job therefore also builds the package and runs
  `twine check --strict` on it. The pre-commit hook doesn't, so a README that breaks
  PyPI's renderer passes locally and fails only in CI.
- The README links to other docs pages by absolute URL on `/en/latest/`, and to
  repository files by GitHub URL, since a relative path resolves differently in each
  renderer. Nothing checks these links. A PyPI page for an older release, or a versioned
  build of the docs site, links to the latest docs.
- The README's headings are the landing page's sections and anchors. Its `contents`
  directive is the landing page's only in-page navigation, since the theme's sidebar
  lists only the toctrees. `autosectionlabel` gives every heading a label in one
  document, so two README headings with the same text fail the strict build, though
  GitHub and PyPI accept them.
- Sphinx applies smart quotes and docutils does not, so a bare `--` or `'` in README
  prose renders differently on the docs site.
- Every type the API page's signatures name must itself be documented there, which is
  why the page carries `VolumeSpec`.
- Any page under `docs/usage/`, nested or not, is published through the landing page's
  `usage/**` glob toctree.

[ADR 0006]: 0006-publish-docs-with-sphinx-and-myst.md
[filters]: https://github.com/todofixthis/filters
