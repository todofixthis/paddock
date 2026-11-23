---
status: Accepted
date: 2026-11-23
scope: [.agents/rules/docs-alerts.md, .autohooks/docs_build.py, .github/workflows/build.yml, .readthedocs.yaml, README.rst, docs/_static/, docs/api.rst, docs/conf.py, docs/index.rst, docs/usage/, pyproject.toml, renovate.json]
summary: Build the docs with Sphinx (not MkDocs), with the user pages under docs/usage/ in reStructuredText (not Markdown through myst-parser), asides as RST admonitions, and a landing page that includes README.rst rather than copying it, so the README must render on GitHub, PyPI and Sphinx alike; build strictly (-W, nitpicky) in a pre-commit hook, CI and ReadTheDocs, without intersphinx.
revisit-when: The docs stop being hosted on ReadTheDocs; a published page needs to cross-reference Python's own documentation; the README needs a construct GitHub, PyPI or Sphinx cannot render; the README stops being RST.
---

# 023: Write the User Docs in reStructuredText

## Context

[ADR 008][] publishes the docs with Sphinx and [myst-parser][]: the user pages under
`docs/usage/` are Markdown, the landing page includes `README.rst`, and every build is
strict. It kept the pages Markdown because converting them would rewrite every page, and
because the rest of `docs/` (ADRs, deferred features, plans) is Markdown.

Markdown was a pre-1.0 convenience for getting the docs up quickly. Since 1.0 the
maintainer wants paddock's docs to converge with the copier template
[todofixthis/cookiecutter-py][cookiecutter-py], which paddock is adopting: its generated
docs are RST, built by Sphinx without myst-parser. Markdown pages also carry costs of
their own here:

- Links between pages use GitHub anchors, which `myst_heading_anchors` has to recreate,
  and asides use GitHub alerts, which need myst-parser's `alert` extension.
- The configuration reference table needs code blocks in its cells, which Markdown
  tables can't hold, so it is a raw HTML table with Markdown inside each cell.
- The user pages, the README and the API page are written in two markup languages.

This ADR restates ADR 008 with the user pages' markup changed, and supersedes it. The
unpublished parts of `docs/` aren't built by Sphinx, so they stay Markdown.

## Options

### Option 1: Do nothing

Keep the user pages Markdown, through myst-parser.

**Pros:** GitHub renders the pages, links included, as it does any Markdown file.
**Cons:** Converging with the template's docs would mean keeping myst-parser and its
settings in a `docs/conf.py` the template owns, a divergence on every template update.

### Option 2: Convert the user pages to RST (Accepted)

Convert the five pages under `docs/usage/` to RST and drop myst-parser.

**Cons:** A one-off rewrite of every page, mechanical but large. On GitHub, the pages'
`:ref:` and `:doc:` links show as raw roles rather than links. Link text can't hold
inline code, so a link to `image` renders as plain linked text. A heading whose text
holds inline code needs an explicit label, since `autosectionlabel` names it after its
raw source.

## Decision

Option 2. The template's docs are RST, so converting now removes the docs divergence
that would otherwise outlive the adoption, and the reference table becomes a
`list-table` rather than raw HTML. The Markdown elsewhere in `docs/` isn't published,
so it never needed one markup with the pages. GitHub is not where readers read the user
pages: the docs site is.

What ADR 008 decided otherwise stands, restated here.

**Toolchain.** Sphinx with the [`sphinx_rtd_theme`][], and autodoc with napoleon for the
[`paddock.agents`][] extension point, mirroring [todofixthis/filters][filters] so
conventions carry between projects. MkDocs would be a second toolchain across the
maintainer's projects, with no autodoc equivalent short of a plugin.

**Strict builds.** A pre-commit hook, CI and ReadTheDocs (`fail_on_warning`) all build
with `-W`; CI does too because `--no-verify` and editor commits skip the hook. `nitpicky`
is on, since without it an unresolved Python cross-reference renders as plain text and
the build stays green. There is no intersphinx: nothing published cites Python's docs,
and fetching its inventory makes every docs-affecting commit depend on the network.

**Published pages.** The README as the landing page, everything under `docs/usage/`, and
the API page. ADRs, deferred features and plans stay unpublished: they are for
contributors and coding agents, read on GitHub.

**The landing page includes the README.** [`docs/index.rst`][] is a single
`.. include:: ../README.rst` followed by hidden toctrees, which drive the sidebar
without rendering on the page. It is the only option with one source and no generator
that keeps the full reference on GitHub and PyPI, where most readers first land.
Copying the README into the docs gives two copies nothing keeps in step; slimming the
README to a pointer moves the quick start away from where readers land; generating the
README from the docs needs a generator, a currency check and a PyPI-safe rendering
Sphinx doesn't produce. RST comment markers could keep the README's link to the docs
site off the docs site, by including the README twice around them. That was tried and
dropped: a link to the page you're on is harmless, and a misplaced marker silently
drops content from the docs site while the build passes.

## Consequences

- An aside is an RST admonition (`.. caution::`, `.. warning::` or `.. note::`), chosen
  and titled as `.agents/rules/docs-alerts.md` says. Troubleshooting entries are a
  definition list, whose terms the theme sets in bold even when a term is all code.
- The `docs` dependency group holds Sphinx and the theme; `dev` includes it so the
  pre-commit hook can build. CI and ReadTheDocs sync with
  `--no-default-groups --group docs`: the project, for autodoc, plus the docs tools.
  Dropping the project (`--only-group`) breaks autodoc.
- A commit staging `README.rst`, `docs/*.rst`, `docs/conf.py`, `pyproject.toml` or
  `src/*.py` runs a full (`-E`), strict Sphinx build; ADR-only commits don't. The hook
  builds the working tree, not the staged snapshot, so an unstaged fix can mask a
  broken staged page; CI builds the commit and catches it.
- Sphinx accepts roles such as `:doc:` and `:ref:` that PyPI's [`readme_renderer`][]
  rejects, so the strict build can't vouch for the PyPI page. CI's `docs` job also
  builds the package and runs [`twine check --strict`][twine] on it. The pre-commit
  hook doesn't, so a README that breaks PyPI's renderer passes locally and fails only
  in CI.
- The README links to other docs pages by absolute URL on `/en/latest/`, and to
  repository files by GitHub URL, since a relative path resolves differently in each
  renderer. Nothing checks these links, and a PyPI page for an older release links to
  the latest docs.
- The README's headings are the landing page's sections and anchors, and its `contents`
  directive the landing page's only in-page navigation. [`autosectionlabel`][] gives
  every heading a document-prefixed label, so two headings with the same text in one
  document fail the strict build, though GitHub and PyPI accept them.
- Sphinx applies smart quotes and docutils does not, so a bare `--` or `'` in prose,
  link text included, renders differently on the docs site.
- Every type the API page's signatures name must itself be documented there, which is
  why the page carries `VolumeSpec`.
- A page directly under `docs/usage/` or `docs/usage/agents/` is published through the
  landing page's `usage/*` and `usage/agents/*` glob toctree; a page nested any deeper
  needs a glob of its own.
- The reference table's `paddock-reference` class keeps the styling in
  `docs/_static/paddock.css`, which pins its header row and directive column.
- Renovate's manager for the Ubuntu tags in the user docs matches `.rst` pages.
- The template also owns `docs/conf.py` and `docs/index.rst`, whose versions have
  intersphinx, no `nitpicky`, and a landing page with no README include or `usage/**`
  toctree. The adoption decides, in an ADR of its own, which of this ADR's settings
  converge with them and which the project keeps.

[ADR 008]: 008-publish-docs-with-sphinx-and-myst-landing-on-the-readme.md
[`autosectionlabel`]: https://www.sphinx-doc.org/en/master/usage/extensions/autosectionlabel.html
[cookiecutter-py]: https://github.com/todofixthis/cookiecutter-py
[`docs/index.rst`]: ../index.rst
[filters]: https://github.com/todofixthis/filters
[myst-parser]: https://myst-parser.readthedocs.io/
[`paddock.agents`]: ../../src/paddock/agents/__init__.py
[`readme_renderer`]: https://github.com/pypa/readme_renderer
[`sphinx_rtd_theme`]: https://sphinx-rtd-theme.readthedocs.io/
[twine]: https://twine.readthedocs.io/
