---
status: Accepted
date: 2026-10-07
scope: [.github/, AGENTS.md, images/Dockerfile, pyproject.toml, renovate.json, uv.lock]
summary: Keep dependencies and pins current with Renovate (config:recommended, Actions pinned by digest, and a regex manager bumping the phx-adr pins together), not Dependabot or hand bumps.
revisit-when: Renovate's pull requests outpace review; the hosted Renovate app stops being available to this repository; Renovate's phx-claude-siat bumps don't resolve to release commits; phx-claude-siat stops tagging releases as bare X.Y.Z versions.
---

# 010: Keep Dependencies Current with Renovate

## Context

Nothing in paddock updates a dependency on its own. The CI workflow pins every Action to
a commit SHA with its version in a trailing comment, the Dockerfile defaults to an
Ubuntu base image tag, and `pyproject.toml` bounds each Python dependency to a major
version; all of these move only when someone notices and edits them.

[ADR 009][] added one more such pin, repeated four times: the `phx-adr` commands in the
`adrs` CI job and `AGENTS.md` all name one phx-claude-siat release commit, and drift
between them and the plugin release sessions load surfaces as a CI stale-index failure.

[`todofixthis/filters-pydantic`][filters-pydantic] already runs Renovate on
`config:recommended` and `helpers:pinGitHubActionDigests`, and [filters-pydantic#63][]
adds a regex custom manager for its own copies of the same `phx-adr` pins.

## Options

### Option 1: Do nothing

**Pros:** No automated pull requests to review.
**Cons:** Every pin and bound is bumped by hand, so it is bumped late or not at all, and
the four `phx-adr` pins have to be kept identical by whoever remembers.

### Option 2: Renovate (Accepted)

Adopt filters-pydantic's configuration: `config:recommended`, Action pins kept as
digests, and a regex custom manager matching each `phx-adr` pin's commit SHA and
trailing version comment.

**Cons:** A trailing version comment on each `phx-adr` command is now load-bearing:
drop it and that pin silently leaves Renovate's view.
**Risks:** Renovate's `github-tags` lookup for the `phx-adr` pins was not run before
adoption, needing a GitHub token; the first bump pull request is its first real test.

### Option 3: Dependabot

**Pros:** Built into GitHub; no app to install.
**Cons:** No custom regex manager, so the `phx-adr` pins stay hand-bumped, and a
different tool and configuration from filters-pydantic.

## Decision

Option 2. It is the only option that keeps the `phx-adr` pins in step without a person
remembering to, and it matches filters-pydantic, so one configuration serves both.

## Consequences

- `renovate.json` holds the configuration; the Renovate app must be installed on this
  repository for it to run.
- The first run opens a burst of pull requests (Actions, Python dependencies, the Ubuntu
  base image, the `phx-adr` pins) and a dependency dashboard issue.
- A base-image bump changes every user's default image, not just a pin: review it as a
  user-facing change, and update the `UBUNTU_VERSION` default and `--image` examples in
  `README.rst` in the same pull request. A local lookup already proposes 24.04 → 26.04.
- Python dependencies move only when a release leaves its major bound, which rewrites
  the bound and `uv.lock`. `config:recommended` leaves `lockFileMaintenance` off, so
  in-range and transitive updates in `uv.lock` are not made; a local lookup proposed
  no Python updates at all.
- The `phx-adr` pins stay at 8.0.0 so that Renovate's first bump exercises the
  `github-tags` lookup. Check its SHA is the release's commit (the `<tag>^{}` line of
  `git ls-remote --tags`), not the tag object, before merging.

[ADR 009]: 009-rely-on-the-phx-plugin-for-adr-tooling.md
[filters-pydantic]: https://github.com/todofixthis/filters-pydantic/blob/main/renovate.json
[filters-pydantic#63]: https://github.com/todofixthis/filters-pydantic/pull/63
