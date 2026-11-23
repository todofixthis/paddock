---
status: Accepted
date: 2026-11-23
scope: [.agents/rules/template-owned.md, .agents/skills/release/, .copier-answers.yml, .github/workflows/, AGENTS.md, pyproject.toml, renovate.json]
summary: Paddock follows the copier template todofixthis/cookiecutter-py, which writes and owns the files .agents/rules/template-owned.md lists, and defers to its decisions in them; cookiecutter-py ADR 019 replaces ADR 009 (ADR tooling), its ADRs 003, 013 and 018 replace ADR 010 (Renovate and the phx-adr pins), and its ADRs 018 and 021 replace ADR 015 (one `gate` job, conditional jobs skipping steps), with paddock's own CI jobs in .github/workflows/project.yml; releases follow the template's release skill, with no release or hotfix branches; diverging from a template decision on purpose needs an ADR here naming the cookiecutter-py ADR it departs from.
revisit-when: Paddock stops taking template updates; the template supersedes or renumbers one of the ADRs named here; ADRs here are routinely authored in a harness other than Claude Code; a fix to a release can't wait for develop's unreleased changes.
---

# 024: Defer to cookiecutter-py's Template Decisions

## Context

Paddock now takes its tooling from [cookiecutter-py's copier template][]
at release 1.4.0, recorded in `.copier-answers.yml`; each later release
arrives as a Renovate PR running `copier update` ([cookiecutter-py ADR
015][]). The files copier writes are template-owned:
[`.agents/rules/template-owned.md`][] lists them and says how to change
one.

Three of paddock's ADRs decide what the template now decides:

- [ADR 009][] relies on the phx plugin for ADR tooling, never a repo-local
  generator, pre-commit hook or vendored copy. [cookiecutter-py ADR 019][]
  decides the same, rejecting the same alternatives.
- [ADR 010][] keeps dependencies current with Renovate, pinning Actions by
  digest and bumping the phx-adr pins with one regex manager.
  [cookiecutter-py ADR 003][], [ADR 013][cookiecutter-py ADR 013] and
  [ADR 018][cookiecutter-py ADR 018] decide the same, adding a weekly lock
  refresh and a three-day release age. The regex managers for the bundled
  Dockerfiles' pins and their copies in the docs are paddock's own, and
  [ADR 016][] decides them.
- [ADR 015][] makes `gate` the only required check, failing on any skip,
  with a conditional job skipping its steps rather than itself.
  cookiecutter-py ADR 018 makes the same `gate` the required check, and
  [ADR 021][cookiecutter-py ADR 021] moves a project's own jobs into
  `.github/workflows/project.yml`, which `gate` needs, under the same
  skip-steps rule. Paddock's `changes`, `image` and README-rendering jobs
  move there.

The template also brings its release skill. Paddock's released through a
`release/v<version>` branch off `develop`, `hotfix/<topic>` branches off
`main`, and a pull request merging `main` back into `develop`. The
template's bumps the version on `develop`, has no hotfix path, and rebases
`develop` onto `main` afterwards.

## Options

### Option 1: Do nothing

Keep ADRs 009, 010 and 015, and paddock's release flow, beside the
template's files.

**Cons:** Two records of each decision, the older describing files the
template now writes: ADR 015's jobs have moved to `project.yml`. A release
skill paddock keeps by hand conflicts with every template update to it.

### Option 2: Defer to the template, superseding 009, 010 and 015 (Accepted)

Take the template's release skill as it stands.

**Cons:** A reader follows a link to another repository for the reasoning,
and the revisit triggers of the template's ADRs sit in the template's
index, where only its maintainer meets them. This ADR names template ADRs
by number, which goes stale if the template supersedes or renumbers one;
the links pin the 1.4.0 tag, so they still lead to the decision paddock
adopted. A fix to the latest release ships with `develop`'s unreleased
changes or waits for them.

### Option 3: Defer to the template but keep paddock's release flow

Option 2, with `.agents/rules/project.md` overriding the release skill's
version bump and back-merge with paddock's release and hotfix branches.

**Cons:** An agent reconciles two release procedures at every release, and
the override has to track each template change to the skill it overrides.

## Decision

Option 2. The template owns these files, so it owns the decisions about
them; a second copy here can only fall behind. The maintainer judged a
hotfix path not worth a release procedure diverging from the template's.
Two triggers can only be seen from inside paddock: ADR 009's, for ADRs
routinely authored outside Claude Code, and a fix that can't wait for
`develop`, so this ADR's `revisit-when` carries both.

## Consequences

- `.agents/rules/template-owned.md` decides whether a change to a
  template-owned file is made here or proposed to cookiecutter-py; that
  rule, not this ADR's `scope`, lists the files.
- Diverging from a template decision on purpose needs its own ADR here,
  naming the template ADR it departs from.
- Paddock's own CI jobs live in `.github/workflows/project.yml`; its
  weekly image build is `.github/workflows/weekly.yml`, calling the same
  workflow.
- The `main and develop` ruleset must require `gate`, which keeps its
  name, and nothing else. The template's release skill pushes the version
  bump straight to `develop`, so the ruleset must allow that push, or the
  bump goes through a pull request.

[ADR 009]: 009-rely-on-the-phx-plugin-for-adr-tooling.md
[ADR 010]: 010-keep-dependencies-current-with-renovate.md
[ADR 015]: 015-gate-ci-on-a-single-required-job.md
[ADR 016]: 016-pin-the-bundled-dockerfiles-installs-and-smoke-test-its-image.md
[`.agents/rules/template-owned.md`]: ../../.agents/rules/template-owned.md
[cookiecutter-py ADR 003]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/003-manage-updates-with-renovate.md
[cookiecutter-py ADR 013]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/013-refresh-lock-files-with-renovate-not-direct-pins.md
[cookiecutter-py ADR 015]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/015-propagate-template-changes-with-copier-and-rotate-python-from-agent-sessions.md
[cookiecutter-py ADR 018]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/018-require-gate-everywhere-and-the-release-check-on-main.md
[cookiecutter-py ADR 019]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/019-rely-on-the-phx-plugin-for-adr-tooling.md
[cookiecutter-py ADR 021]: https://github.com/todofixthis/cookiecutter-py/blob/1.4.0/docs/adr/021-run-a-project-s-own-ci-jobs-in-a-workflow-the-gate-calls.md
[cookiecutter-py's copier template]: https://github.com/todofixthis/cookiecutter-py
