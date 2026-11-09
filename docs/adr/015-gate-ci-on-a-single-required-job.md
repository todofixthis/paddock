---
status: Accepted
date: 2026-11-09
scope: [.github/workflows/]
summary: Branch protection requires only a gate job that depends on every other CI job and fails on any result but success, a skip included unless the job's own change detection skipped it, rather than requiring each job by name.
revisit-when: GitHub branch protection can require a check that a path filter skipped without blocking the merge; a workflow other than build.yml needs its own required check.
---

# 015: Gate CI on a Single Required Job

## Context

[ADR 016][] adds an `image` job that builds the bundled Dockerfile only when a change
touches it. A required check that never reports holds a pull request open forever, so a
workflow-level `paths` filter can't be used for it. A job skipped by its `if:` reports
success instead, so requiring the `image` job by name would pass a run that skipped it by
mistake, such as one whose change detection broke.

Requiring each job by name also means updating branch protection, a platform setting no
file in this repository records, for every job added, renamed or split.

[`todofixthis/cookiecutter-py`][cookiecutter-py] already ends its CI with a `gate` job,
the only required check, which fails on any result but success.
[`todofixthis/config-paddock`][config-paddock] has a gate too, beside a path-conditioned
image build, and lets any skip pass.

## Options

### Option 1: Do nothing

Require each job by name in branch protection.

**Cons:** A path-conditioned job can't be required without passing on any skip. Every job
change needs a matching edit to a setting nobody reviews.

### Option 2: One gate that only passes skips it can account for (Accepted)

A `gate` job runs with `if: always()`, needs every other job, and fails unless each
succeeded. The one exception is `image`, which may be skipped when the `changes` job
reported nothing to build.

**Cons:** The gate lists every job, so a new job left out of `needs` is unguarded. It also
fails on a run cancelled by a newer push, leaving that superseded commit red.

### Option 3: One gate that passes any skip

config-paddock's form: fail only on `failure` or `cancelled`.

**Cons:** A job skipped by a broken condition passes unnoticed, which is the gap Option 1
leaves for `image`.

## Decision

Option 2. It keeps cookiecutter-py's guarantee that a skip can't pass unnoticed while
allowing the one skip that change detection justifies, and it moves the list of required
checks out of a platform setting into a reviewed file. `always()`, not `!cancelled()`:
GitHub counts a skipped required check as passing, so a gate skipped on cancellation would
make the cancelled commit mergeable untested.

## Consequences

- Branch protection on `develop` and `main` must require `gate` and nothing else. This is
  a repository setting a maintainer changes by hand.
- A new job must be added to the gate's `needs`, or it can fail without blocking a merge.
- A new path-conditioned job needs its own exception in the gate, keyed to the change
  detection that skips it, not a blanket pass for skips.

[ADR 016]: 016-pin-the-bundled-dockerfiles-installs-and-smoke-test-its-image.md
[config-paddock]: https://github.com/todofixthis/config-paddock/blob/main/.github/workflows/build.yml
[cookiecutter-py]: https://github.com/todofixthis/cookiecutter-py/blob/develop/.github/workflows/ci.yml
