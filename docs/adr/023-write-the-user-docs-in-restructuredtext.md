---
status: Accepted
date: 2026-11-23
scope: [.agents/rules/docs-alerts.md, .autohooks/docs_build.py, .github/workflows/build.yml, .readthedocs.yaml, README.rst, docs/api.rst, docs/conf.py, docs/index.rst, docs/usage/, pyproject.toml, renovate.json]
summary: Write the user pages under docs/usage/ in reStructuredText, built by Sphinx without myst-parser, with asides as RST admonitions (`.. caution::`), not GitHub alerts; otherwise ADR 008 stands, restated here, with README.rst included as the landing page, strict (-W) builds in the pre-commit hook, CI and ReadTheDocs, nitpicky on, and twine check on the README in CI.
revisit-when: The docs stop being hosted on ReadTheDocs; the README needs a construct GitHub, PyPI or Sphinx cannot render; the README stops being RST.
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
- The pages, the README and the API page are written in two markup languages.

The unpublished parts of `docs/` aren't built by Sphinx, so they can stay Markdown.

## Options

### Option 1: Do nothing

Keep the user pages Markdown.

**Cons:** Converging with the template's docs would mean keeping myst-parser and its
configuration in a `docs/conf.py` the template owns, a divergence on every template
update.

### Option 2: Convert the user pages to RST (Accepted)

Convert the five pages under `docs/usage/` to RST and drop myst-parser.

**Cons:** A one-off rewrite of every page, mechanical but large. Cross-page links become
`:ref:` and `:doc:` roles, whose link text can't hold inline code, so a link to
`` `image` `` renders as plain linked text. A heading whose text holds inline code gets
an explicit label, since `autosectionlabel` names it after its raw source.

## Decision

Option 2. The template's docs are RST, so converting now removes the one docs divergence
that would otherwise outlive the adoption, and the reference table becomes a plain
`list-table` rather than raw HTML. The Markdown elsewhere in `docs/` isn't published, so
it never needed one markup with the pages.

Everything else ADR 008 decided stands, restated here:

- The landing page is a single `.. include:: ../README.rst` plus hidden toctrees, so the
  README renders on GitHub, PyPI and Sphinx alike, from one source.
- The pre-commit hook, CI and ReadTheDocs (`fail_on_warning`) all build strictly
  (`-W`), and `nitpicky` is on. CI also runs `twine check --strict` on the built
  package, since Sphinx accepts roles PyPI's renderer rejects.
- The published pages are the README, everything under `docs/usage/` and the API page;
  ADRs, deferred features and plans stay unpublished.

## Consequences

- An aside is an RST admonition (`.. caution::`, `.. warning::` or `.. note::`), chosen
  as `.agents/rules/docs-alerts.md` says; GitHub no longer renders the user pages as
  styled Markdown.
- The `docs` dependency group drops myst-parser, `docs/conf.py` drops its MyST settings
  and `source_suffix`, and the pre-commit hook no longer builds the docs for a staged
  `docs/*.md`, so ADR-only commits skip the Sphinx build.
- Renovate's manager for the Ubuntu tags in the user docs matches `.rst` pages.
- Converging the rest of the Sphinx configuration with the template, intersphinx and
  `nitpicky` included, belongs to the adoption.

[ADR 008]: 008-publish-docs-with-sphinx-and-myst-landing-on-the-readme.md
[cookiecutter-py]: https://github.com/todofixthis/cookiecutter-py
[myst-parser]: https://myst-parser.readthedocs.io/
