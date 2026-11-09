---
status: Accepted
date: 2026-11-09
scope: [images/Dockerfile, renovate.json, README.rst, docs/usage/, .github/scripts/, .github/workflows/build.yml]
summary: Pin each version images/Dockerfile installs in an ARG with a renovate annotation, bump each pin and its copies in README.rst and docs/usage/ in one Renovate pull request, and build and smoke-test the image in CI for each agent whenever it changes; not unpinned installs, and not hand-kept doc copies.
revisit-when: Renovate's Dockerfile and docs pull requests outpace review; a pin's datasource stops matching what the Dockerfile installs from, as deadsnakes or NodeSource lagging a new Ubuntu release would.
---

# 016: Pin the Bundled Dockerfile's Installs and Smoke-Test Its Image

## Context

[`images/Dockerfile`][Dockerfile] installs Claude Code and OpenCode unpinned. [ADR 011][]
left freshness to the Dockerfile and documents pinning with Renovate as the best fix, yet
the bundled Dockerfile was the docs' own example of a stale install.

The Dockerfile's defaults are also copied into docs: the build-arguments table in
[`README.rst`][README] and the `ubuntu:` tags in it and [`docs/usage/`][usage].
[ADR 010][] has the person merging a base-image bump update those copies in the same pull
request. Renovate's base-image bump, `7899b2f`, changed only the Dockerfile, and the README
fell behind.

Nothing builds the Dockerfile in CI, so a bump that breaks the build or installs an
unexpected version reaches users first. Ubuntu 26.04 was adopted without a build.

## Options

All options but the first build and smoke-test the image in CI, since an automated bump
that nothing builds is untested. That cost doesn't rank them.

### Option 1: Do nothing

**Cons:** Agents stay unpinned, so a cached rebuild never updates them (ADR 011's stale
install). Doc copies drift on every bump, and a broken Dockerfile ships unnoticed.

### Option 2: Pin every install, and let Renovate bump the doc copies with it (Accepted)

Each version the Dockerfile installs (Claude Code, Node.js, OpenCode, Python) moves to an
`ARG` with a `# renovate:` annotation, which a regex manager reads, as in
[`todofixthis/config-paddock`][config-paddock]. Regex managers over `README.rst` and
`docs/usage/` match each copy of a default, and each copy shares its pin's dependency name,
so Renovate puts both in one branch. A `groupName` does the same for Ubuntu, which
Renovate's Dockerfile manager finds without an annotation.

**Cons:** One regex manager per README row, each a pattern that silently stops matching
if the row's layout changes. Claude Code's stable tag moves about weekly, so pull requests
increase. The README table becomes a `list-table`: Renovate replaces a value without
re-padding, which breaks a grid table whenever a value's width changes.
**Risks:** The Python and Node.js datasources describe CPython and Node.js releases, not
what deadsnakes or NodeSource publish for a given Ubuntu release, so Renovate can propose
a version they don't package.

### Option 3: Pin every install, and check the doc copies in CI

Pin as in Option 2, but have CI fail when a doc copy differs from the Dockerfile.

**Cons:** Every Renovate bump goes red until someone edits the copies by hand: about weekly
for Claude Code alone.

## Decision

Option 2. It applies the fix ADR 011 recommends to paddock's own Dockerfile, and it turns
ADR 010's same-pull-request rule into something Renovate does rather than something a
reviewer remembers. Option 3 catches drift but makes fixing it a recurring manual chore.

The smoke test reads its expectations from the Dockerfile's `ARG` defaults, so a bump is
checked against what it installed. It covers each agent, since each takes a different
`RUN` branch. The datasource risk is what the CI build exists to catch.

## Consequences

- Merging a pin bump changes what users' builds install. Review an agent's pull request
  as a user-facing change, as ADR 010 already does for the base image.
- A new install in the Dockerfile needs an annotated `ARG`. Its README row then needs its
  own regex manager, or it drifts.
- Python's pin keeps `major.minor` through an `extractVersion` rule, because deadsnakes
  names packages that way. Node.js keeps its major, under Renovate's `node` versioning,
  which proposes only LTS releases.
- The Python lookup could not be dry-run when this was written: Renovate's `python-version`
  datasource needs GitHub's API, which the authoring environment blocked. Its first
  pull request is its first real test.

[ADR 010]: 010-keep-dependencies-current-with-renovate.md
[ADR 011]: 011-track-build-time-in-an-image-label.md
[config-paddock]: https://github.com/todofixthis/config-paddock/blob/main/renovate.json
[Dockerfile]: ../../images/Dockerfile
[README]: ../../README.rst
[usage]: ../../docs/usage/
