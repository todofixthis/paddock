---
status: Accepted
date: 2026-11-09
scope: [images/Dockerfile, renovate.json, README.rst, docs/usage/, .github/scripts/, .github/workflows/build.yml]
summary: Pin each version images/Dockerfile installs in an ARG with a renovate annotation, let Renovate bump each pin and its copies in README.rst's list-table (one regex manager per row) and the docs' ubuntu tags in one pull request, and build and smoke-test the image per agent on each change and weekly; not unpinned installs, and not hand-kept or linked-only doc copies.
revisit-when: Renovate's Dockerfile and docs pull requests outpace review; a pin's datasource stops matching what the Dockerfile installs from, as deadsnakes or NodeSource lagging a new Ubuntu release would; the scheduled build breaks often enough that the unpinned apt, PPA and NodeSource inputs need pinning too; paddock publishes the bundled image to a registry.
---

# 016: Pin the Bundled Dockerfile's Installs and Smoke-Test Its Image

## Context

[`images/Dockerfile`][Dockerfile] installs Claude Code and OpenCode unpinned. [ADR 011][]
left freshness to the Dockerfile and documents pinning with Renovate as the best fix, yet
the bundled Dockerfile was the docs' own example of a stale install.

The Dockerfile's defaults are also copied into docs: the build-arguments table in
[`README.rst`][README] and the `ubuntu:` tags in it and [`docs/usage/`][usage].
[ADR 010][] has the person merging a base-image bump update the README in the same pull
request. Renovate's base-image bump, `7899b2f`, changed only the Dockerfile, and the README
fell behind.

Nothing builds the Dockerfile in CI, so a bump that breaks the build reaches users first.
Ubuntu 26.04 was adopted without a build.

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
`docs/usage/` match each copy; a copy shares its pin's dependency name, so Renovate puts
both in one branch.

**Cons:** One regex manager per README row, each a pattern that silently stops matching if
the row's layout changes. Claude Code's `stable` tag moves often, so pull requests
increase.
**Risks:** The Python and Node.js datasources describe CPython and Node.js releases, not
what deadsnakes or NodeSource publish for a given Ubuntu release, so Renovate can propose
a version they don't package.

### Option 3: Pin every install, and link to the Dockerfile instead of copying

README rows name each `ARG` and point to `images/Dockerfile` for its default.

**Cons:** Readers leave the README to learn which Node.js, Python or agent version they
get.

### Option 4: Pin every install, and check the doc copies in CI

CI fails when a copy differs from the Dockerfile.

**Cons:** Every Renovate bump goes red until someone edits the copies by hand.

## Decision

Option 2. It applies the fix ADR 011 recommends to paddock's own Dockerfile, and turns
ADR 010's same-pull-request rule into something Renovate does rather than something a
reviewer remembers. The maintainer chose to keep the defaults readable in the README over
Option 3's simpler configuration; Option 4 catches drift but makes fixing it a recurring
manual chore.

The CI build proves each bump builds and that each agent's binary runs. Most version
checks in the smoke test restate what a successful build already guarantees; the Node.js
major is the exception, since `apt-get install nodejs` can fall back to Ubuntu's own
package when NodeSource has none for the release. A weekly build covers the inputs that
stay unpinned (apt packages, the deadsnakes PPA, NodeSource's setup script, the Ubuntu
tag's digest), which can break the build without a commit.

## Consequences

- The README table is a `list-table` with one `- ``value``` line under each
  `* - ``ARG``` line. Renovate replaces a value without re-padding, which would break a
  grid table whenever the value's width changed, and each row's regex manager matches
  that layout.
- A new install in the Dockerfile needs an annotated `ARG`, and its README row its own
  regex manager, or the row drifts.
- Every `ubuntu:NN.NN` in `README.rst` and `docs/usage/` follows the base image, examples
  included. An example that must name an older release needs a form the pattern skips.
- Merging a pin bump changes what users' builds install: review it as a user-facing
  change, as ADR 010 does for the base image.
- Each change to `images/`, the smoke script or the CI workflow builds the image three
  times, once per agent; Renovate's Actions bumps touch the workflow, so they do too.
- Python's pin keeps `major.minor` through an `extractVersion` rule, because deadsnakes
  names packages that way. Node.js keeps its major under Renovate's `node` versioning,
  which proposed 26 from 22, skipping the non-LTS 23 and 25.
- The Python lookup could not be dry-run when this was written: Renovate's `python-version`
  datasource needs GitHub's API, which the authoring environment blocked. Its first pull
  request is its first real test.

[ADR 010]: 010-keep-dependencies-current-with-renovate.md
[ADR 011]: 011-track-build-time-in-an-image-label.md
[config-paddock]: https://github.com/todofixthis/config-paddock/blob/main/renovate.json
[Dockerfile]: ../../images/Dockerfile
[README]: ../../README.rst
[usage]: ../../docs/usage/
