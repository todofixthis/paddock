---
status: Accepted
date: 2026-11-17
scope: [images/, src/paddock/agents/, pyproject.toml, .github/workflows/build.yml, .github/scripts/, renovate.json, README.rst, docs/usage/]
summary: images/ holds one Dockerfile per bundled agent, named <agent>.Dockerfile (claude.Dockerfile, opencode.Dockerfile), each complete in itself and pinned and smoke-tested as ADR 016 requires; not one Dockerfile holding every agent's install, not a shared base image, and not one multi-stage file with a target per agent; every bundled agent still passes AGENT to its build, so each file declares it, and claude.Dockerfile keeps its claude and none cases, none being what agent = false builds; OpenCode's one file serves both its client and its server.
revisit-when: The toolchain steps the Dockerfiles repeat are found to have drifted apart; paddock publishes images to a registry; a bundled agent needs more than one image, as OpenCode's client and server might.
---

# 022: Give Each Bundled Agent Its Own Dockerfile

## Context

Paddock bundled one Dockerfile, `images/Dockerfile`, which installed a toolchain
and then the agent its `AGENT` build argument named: `claude`, or `none` for no
agent. [ADR 016][] pins what it installs and smoke-tests an image per agent.
[ADR 019][] expected each agent whose server it can build to become a further
case in that file, and OpenCode was first added that way.

Three things press against one file:

- **It is the documentation.** A user building their own image for an agent
  reads the bundled file to learn what that agent needs. One file for every
  agent shows them a `case` statement, pins for agents they do not use, and
  nothing about what is particular to theirs.
- **The agents' images are diverging.** OpenCode's serves two containers, a
  server that needs the toolchain and a client that runs none of the agent's
  tools ([ADR 018][]).
- **Paddock may publish images.** One image per agent, from a registry, wants
  one build definition per image.

## Options

Every option keeps ADR 016's pins, README copies and per-agent smoke test, so
that cost does not rank them.

### Option 1: Do nothing

One `images/Dockerfile`, with a case for each agent.

**Pros:** The toolchain steps exist once.
**Cons:** A reader cannot see one agent's image without reading every agent's.
**Risks:** Each agent that differs by more than an install line adds a
conditional, and the file stops being readable as an example of anything.

### Option 2: One Dockerfile per agent (Accepted)

`images/<agent>.Dockerfile`, each complete in itself: `claude.Dockerfile`, which
is the released file under a new name, and `opencode.Dockerfile`.

**Pros:** Each file is a whole, copyable example for its agent, and the unit a
published image would be built from.
**Cons:** The toolchain steps (base image, Python, Node.js) and their pins are
repeated in each file.
**Risks:** The repeated steps drift: a fix made in one file and not the other.

### Option 3: A shared base image, and a thin Dockerfile per agent

A base Dockerfile installs the toolchain; each agent's starts `FROM` it.

**Pros:** No repeated steps, and small per-agent files.
**Cons:** Nothing paddock runs can build an agent's image in one step: the base
must be built and tagged first, which `build.dockerfile` cannot do, or
published somewhere to pull from.
**Risks:** A user copying an agent's file gets one that does not build without
the other.

### Option 4: One multi-stage Dockerfile, with a target per agent

A toolchain stage and a stage per agent, the last `FROM` choosing one by the
`AGENT` argument.

**Pros:** No repeated steps, one build step, no registry.
**Cons:** The file is every agent's again, as in Option 1, and harder to read
than Option 1's `case`.
**Risks:** An `AGENT` that names no stage fails with a message about a missing
image, not an unknown agent.

## Decision

Option 2. The files are examples first. An example that needs a second file to
build is a worse one, which rules out Option 3 until there is a registry to
hold the base, and Option 4 gives back the one file a reader must take whole. The repetition Option 2 costs is three install steps,
and Renovate bumps a pin in every file that carries it in one pull request, so
the pins cannot drift by neglect; the steps themselves can, which is the
revisit trigger.

**Names.** `<agent>.Dockerfile`, where `<agent>` is the agent's key. Renovate's
Dockerfile manager and editors both recognise the suffix.

**OpenCode has one file for both containers.** The client needs OpenCode at the
server's version and nothing else, so a client-only file would be smaller, but
two files mean two pins to keep equal and two images to build before a first
run. One image for both removes the mismatch.

**`AGENT` stays.** Each bundled agent still passes its build its name, because
a user's own Dockerfile may branch on it, so every bundled file declares it.
`claude.Dockerfile` is the released file unchanged, the OpenCode case having
been added and removed again before any release: it keeps its `claude` and `none`
cases, `none` being the image `agent = false` builds, and its default of `none`.
That default sits oddly under the file's name, since a bare `docker build` of
it installs no agent; the bundled agents always pass the argument, and changing what
the renamed file builds was not part of renaming it. `opencode.Dockerfile`
installs OpenCode whatever the argument says.

## Consequences

- A user's `build.dockerfile` pointing at `images/Dockerfile` in a checkout
  stops resolving when they pull, and the run stops with the path error. The
  release notes must say the file is now `images/claude.Dockerfile`.
- ADR 016's rules now apply per file: a new install needs its annotated `ARG`
  in each file that installs it, and each file is built and smoke-tested in CI.
- ADR 019's expectation that the one file gains a case per server-building
  agent is replaced: such an agent gains a file.
- A change to the toolchain steps is made in every file. Nothing checks that
  they agree.
- A new bundled agent costs a Dockerfile, a leg in the CI matrix, a case in the
  smoke test (and its command in the `none` case's list), its README rows, and
  a Renovate manager for each row, without which the row silently stops being
  bumped (ADR 016).
- `opencode.Dockerfile` no longer refuses an agent it does not know. Pointed at
  it, `agent = "claude"` builds an image without Claude and fails when the
  container starts, where the one file failed at the build.
- The image with no agent has no file of its own: it is `claude.Dockerfile`
  built with `AGENT=none`.
- Publishing the images is a [backlog item][published images].

[ADR 016]: 016-pin-the-bundled-dockerfiles-installs-and-smoke-test-its-image.md
[ADR 018]: 018-split-agents-into-clients-and-servers.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
[published images]: ../future/published-base-images.md
