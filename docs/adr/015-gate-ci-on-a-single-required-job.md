---
status: Accepted
date: 2026-11-09
scope: [.github/workflows/, .agents/skills/rotate-python-versions/]
summary: The main and develop ruleset requires only a gate job that runs under always() (not !cancelled()), needs every other CI job, and fails on any result but success, a skip included; a job that may have nothing to do skips its steps, never itself.
revisit-when: GitHub rulesets can require a check that a condition skipped without passing it unnoticed; CI gains a pull_request or merge_group trigger, or a merge queue; a workflow other than build.yml needs its own required check.
---

# 015: Gate CI on a Single Required Job

## Context

The `main and develop` ruleset requires seven checks by name: `adrs`, `docs`, `lint`,
`typecheck` and one per test matrix leg (`test (3.12)` to `test (3.14)`). Adding, renaming
or splitting a job, or rotating a Python version, means editing the ruleset, a platform
setting that no file in this repository records. Miss one and a required check for a
removed job never reports, blocking every pull request.

[ADR 016][] adds an `image` job with nothing to do unless a change touches the Docker
image. A required check that never reports blocks merging, so a workflow-level `paths`
filter can't skip it. A job skipped by its `if:` reports success, so a required `image`
job would pass a run that skipped it by mistake, such as one whose change detection broke.

[`todofixthis/cookiecutter-py`][cookiecutter-py] already ends its CI with a `gate` job,
the only required check, which fails on any result but success.
[`todofixthis/config-paddock`][config-paddock] has a gate beside a job-level
path-conditioned build, and lets any skip pass.

## Options

### Option 1: Do nothing

Keep requiring each job by name.

**Cons:** Every job or matrix change needs a matching ruleset edit. `image` can't be
required without passing any skip.

### Option 2: One gate failing on any skip; conditional jobs skip steps (Accepted)

cookiecutter-py's gate, unchanged. `image` always runs, and its build and smoke steps skip
only when the `changes` job reported an explicit `false`, so the job still reports success
or failure, and broken change detection builds rather than skipping.

**Cons:** Each push starts an `image` runner per agent that does nothing for a few seconds.

### Option 3: One gate that excuses a skip change detection justifies

`image` skips as a job; the gate passes that skip only when `changes` reported nothing to
build.

**Cons:** The gate carries an exception per conditional job, keyed to that job's change
detection, and grows with each one.

### Option 4: One gate that passes any skip

config-paddock's form: fail only on `failure` or `cancelled`.

**Cons:** A job skipped by a broken condition passes unnoticed.

## Decision

Option 2. A single gate takes the list of required checks out of the ruleset and into a
reviewed file. Conditioning steps rather than jobs lets the gate stay cookiecutter-py's
plain rule, with no exceptions to keep in step with each job's change detection, for the
price of a few idle runner-seconds.

`always()`, not `!cancelled()`: GitHub counts a skipped required check as passing, so a
gate skipped on cancellation would make the cancelled commit mergeable untested. Nothing
here cancels superseded runs, so only a manual cancel or a job timeout leaves a commit red.

## Consequences

- The `main and develop` ruleset must require `gate` and nothing else. A maintainer
  changes it by hand.
- A new job must join the gate's `needs`, or it can fail without blocking a merge.
- A job that may have nothing to do conditions its steps, not itself, and skips them only
  on an explicit negative output (`!= 'false'`, not `== 'true'`), so that a broken
  condition fails safe.
- Rotating Python versions no longer touches the ruleset; the rotate-python-versions
  skill says so.

[ADR 016]: 016-pin-the-bundled-dockerfiles-installs-and-smoke-test-its-image.md
[config-paddock]: https://github.com/todofixthis/config-paddock/blob/main/.github/workflows/build.yml
[cookiecutter-py]: https://github.com/todofixthis/cookiecutter-py/blob/develop/.github/workflows/ci.yml
