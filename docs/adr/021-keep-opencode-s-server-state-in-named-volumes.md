---
status: Accepted
date: 2026-11-17
scope: [src/paddock/agents/, docs/usage/]
summary: OpenCode's server keeps its data and state directories in two named Docker volumes that Paddock creates, and its client keeps its interface state in a named volume of its own; neither mounts the host's OpenCode directories, and the server has no default image, so agents.opencode.server.image is required.
revisit-when: OpenCode gains a lock that stops two processes opening one database; users need the host's OpenCode sessions or sign-in inside Paddock; OpenCode moves credentials out of its data directory; Paddock publishes an image a server could default to; a version mismatch between client and server stops working.
---

# 021: Keep OpenCode's Server State in Named Volumes

## Context

[ADR 018][] makes OpenCode a client and a server, and [ADR 019][] runs the server
in one long-lived container that Paddock removes and recreates when it has stopped
or when the user changes its mounts. Whatever the server keeps in its container's
own filesystem is lost at that point, so its state needs a home outside it.

Checked against OpenCode 2.3.0 in containers on 2026-11-17, running as root:

- The server writes its database, `opencode.db`, with its logs, under
  `/root/.local/share/opencode`, and creates `/root/.config/opencode` and
  `/root/.local/state/opencode`. The database holds sessions and, read in the
  2.3.0 source on 2026-11-15, the provider credentials a user signs in with.
- The interactive client writes only interface state, under
  `/root/.local/state/opencode`, and a log.
- Nothing stops two processes opening one database. That is what corrupted state
  in the reverted first attempt ([#53][]).
- An `opencode` started on the host without `--server` runs a background service
  of its own against the host's data directory.

The server also runs every tool, so its image is the environment the agent works
in, and Paddock builds no image a user has not asked for.

## Options

### Option 1: Do nothing

The server and client keep their files in their containers' own filesystems.

**Pros:** Nothing to create or name.
**Cons:** Recreating the server, which adding a mount requires, discards every
session and the sign-in. The client loses its interface state on every run.
**Risks:** Users avoid recreating the server, and so avoid adding mounts.

### Option 2: Named volumes Paddock creates (Accepted)

The server's data and state directories are two named volumes, and the client's
state directory a third. No host directory of OpenCode's is mounted.

**Pros:** State outlives the container. Only the one server ever opens the
database.
**Cons:** A host OpenCode and Paddock's do not share sessions, settings or
sign-in. The files are reachable only through Docker.
**Risks:** `docker volume prune -a` removes them once no container holds them,
sign-in included; without `-a` Docker leaves named volumes alone.

### Option 3: Mount the host's OpenCode directories

As the `claude` agent mounts `~/.claude`: the host's `~/.local/share/opencode`
and its siblings, read-write, into the server.

**Pros:** One set of sessions, settings and sign-in for host and Paddock.
**Cons:** The paths differ by platform, and the host's database then carries
paths and state from a Linux container.
**Risks:** A host `opencode` run beside a Paddock server puts two processes on
one database, the fault #53 was reverted for, and nothing warns before it does.

## Decision

Option 2. Option 3's risk is the one failure this work exists to remove, and it
would be reached by ordinary use: nothing about running `opencode` on the host
looks wrong. Sharing sign-in with the host is not worth a corruptible database.

The volumes are named for the server, not the image, since there is one server:
`paddock-server-opencode-data` and `paddock-server-opencode-state`, at
`/root/.local/share/opencode` and `/root/.local/state/opencode`. The config
directory, `/root/.config/opencode`, gets no volume: it holds settings a user
writes, so it is theirs to mount. The client's is `paddock-client-opencode-state`,
at `/root/.local/state/opencode`: one whatever the image, the state being the
interface's and not the image's. The cache directory is left to the container.

**The server has no default image.** `agents.opencode.server.image` is required,
and a run without it stops with ADR 019's message. Any default would be an image
without the user's toolchain, which the first tool call would then expose; the
bundled Dockerfile with `AGENT=opencode` is the documented starting point for
both the server's image and the client's.

## Consequences

- Sign-in happens once, through a Paddock-launched client, and survives the
  server being recreated. It does not carry over from a host install.
- Removing the two server volumes resets OpenCode for every project. The docs
  name them.
- The paths assume the container runs as root with default XDG directories, as
  Paddock's images already must. An image that sets `XDG_DATA_HOME` elsewhere
  keeps its state in the container, where recreating the server loses it.
- A user who wants the host's OpenCode settings in the server mounts that
  directory themselves under `agents.opencode.server.volumes`, at
  `/root/.config/opencode`; the database is the part that must not be shared.
  Without that mount, anything OpenCode writes to its config directory is lost
  when the server is recreated.

[#53]: https://github.com/todofixthis/paddock/pull/53
[ADR 018]: 018-split-agents-into-clients-and-servers.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
