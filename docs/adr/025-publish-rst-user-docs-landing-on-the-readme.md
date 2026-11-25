---
status: Accepted
date: 2026-11-23
scope: [.agents/rules/project.md, .agents/skills/release/, .autohooks/docs_build.py, .github/workflows/project.yml, README.rst, docs/]
summary: Publish the docs with Sphinx (not MkDocs), the user pages under docs/usage/ in reStructuredText (not Markdown through myst-parser), and a landing page that includes README.rst rather than copying it, so the README must render on GitHub, PyPI and Sphinx alike, which project.yml's readme job checks with twine; strict builds, intersphinx and the rest of docs/conf.py follow cookiecutter-py's template (its ADR 020), which has no nitpicky.
revisit-when: The docs stop being hosted on ReadTheDocs; the README needs a construct GitHub, PyPI or Sphinx cannot render; the README stops being RST; the template's docs/conf.py gains nitpicky; cookiecutter-py declines nitpicky; an unresolved cross-reference reaches the published docs.
---

# 025: Publish RST User Docs Landing on the README

## Context

[ADR 023][] publishes paddock's docs with Sphinx, the user pages under
`docs/usage/` in RST, and a landing page that includes `README.rst`. It
also builds strictly with `nitpicky` on and no intersphinx, and left the
adoption of [cookiecutter-py's template][] to decide which of its settings
converge with the template's.

The template now owns `docs/conf.py`, the docs pre-commit hook and the
docs CI job. Its `conf.py` enables intersphinx for Python's docs and has
no `nitpicky`; its hook and CI job build with `-W` ([cookiecutter-py ADR
020][]). `docs/index.rst` and `README.rst` are seed files, which paddock
owns.

## Options

### Option 1: Do nothing

Keep ADR 023's settings in the template's `conf.py`: `nitpicky` with its
ignore list, no intersphinx, and the unpublished directories excluded.

**Cons:** A template-owned file diverges in several places, conflicting on
template updates for reasons nothing about paddock requires.

### Option 2: Restate ADR 023, taking the template's conf.py (Accepted)

Keep paddock's own decisions (Sphinx, RST pages, the README landing page,
its PyPI check) and take the template's `conf.py` whole, adding only the
stylesheet for the reference table.

**Cons:** An unresolved Python cross-reference renders as plain text and
the build stays green until the template turns `nitpicky` on. Every
docs-affecting build fetches Python's intersphinx inventory, so it needs
the network.

## Decision

Option 2. Nothing in `nitpicky` or intersphinx is specific to paddock, so
each belongs to the template; `nitpicky` is proposed to it, and paddock
builds without warnings with it on. What ADR 023 decided otherwise stands,
restated here.

**Toolchain.** Sphinx with the `sphinx_rtd_theme`, and autodoc with
napoleon for the [`paddock.agents`][] extension point, as the template
generates.

**Published pages.** The README as the landing page, everything under
`docs/usage/`, and the API page. ADRs, deferred features and plans are
Markdown, which Sphinx doesn't read without myst-parser, so they stay
unpublished without the `exclude_patterns` entries ADR 023 kept for them.

**The landing page includes the README.** [`docs/index.rst`][] is a single
`.. include:: ../README.rst` followed by hidden toctrees. It is the only
option with one source and no generator that keeps the full reference on
GitHub and PyPI, where most readers first land; ADR 023 weighs the
alternatives.

## Consequences

- An aside is an RST admonition, chosen and titled as the template's
  `.agents/rules/docs-admonitions.md` says. Troubleshooting entries are a
  definition list.
- The docs pre-commit hook builds for a staged `README.rst` as well as the
  template's paths, because the landing page includes it: a line paddock
  adds to the template-owned hook.
- Sphinx accepts roles that PyPI's renderer rejects, so the strict build
  can't vouch for the PyPI page: `project.yml`'s `readme` job builds the
  package and runs `twine check --strict`. The pre-commit hook doesn't.
- The README links to other docs pages by absolute URL on `/en/latest/`,
  and to repository files by GitHub URL, since a relative path resolves
  differently in each renderer. Nothing checks these links, and an older
  release's PyPI page links to the latest docs.
- The README's headings are the landing page's sections, and its
  `contents` directive the landing page's only in-page navigation. Two
  headings with the same text fail the strict build through
  `autosectionlabel`, though GitHub and PyPI accept them.
- Sphinx applies smart quotes and docutils does not, so a bare `--` or `'`
  in README prose, link text included, renders differently on the docs
  site.
- A page directly under `docs/usage/` or `docs/usage/agents/` is published
  through the landing page's glob toctrees; a page nested deeper needs a
  glob of its own.
- The template's release skill wires a migration guide into an
  upgrade-alert listing in both `docs/index.rst` and `README.rst`, linked
  from the README ~~by relative path~~ by absolute URL from cookiecutter-py
  1.6.0. Paddock's index includes the README, so
  the listing goes in the README alone, linked by absolute URL;
  `.agents/rules/project.md` overrides the skill to say so.
- The reference table's `paddock-reference` class keeps the styling in
  `docs/_static/paddock.css`, which `docs/conf.py` loads: a line paddock
  adds to the template-owned file.

[ADR 023]: 023-write-the-user-docs-in-restructuredtext.md
[cookiecutter-py ADR 020]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/020-fail-generated-docs-builds-on-sphinx-warnings-in-ci-and-before-commit.md
[cookiecutter-py's template]: https://github.com/todofixthis/cookiecutter-py
[`docs/index.rst`]: ../index.rst
[`paddock.agents`]: ../../src/paddock/agents/__init__.py
