---
status: Accepted
date: 2026-11-17
scope: [src/paddock/agents/, src/paddock/docker/, images/Dockerfile, docs/usage/]
summary: By default OpenCode's server keeps its data and state directories in two named Docker volumes (paddock-server-opencode-data and -state, under /root/.local) and its client keeps its interface state in a third (paddock-client-opencode-state), apart from the host's OpenCode; a user may opt into sharing by mounting a host directory at one of those paths under agents.opencode.server.volumes, which replaces the named volume there, and Paddock never does so unasked; the config and cache directories deliberately get no volume, and the server has no default image, so agents.opencode.server.image is required.
revisit-when: OpenCode gains a lock that stops two processes opening one database; a shared database is found corrupted; Paddock can warn about an accepted risk and let the user silence that warning; OpenCode moves its database, credentials or directory layout; Paddock runs containers as a user other than root; a server can have more than one instance; an image exists that carries a typical user's toolchain.
---

# 021: Keep OpenCode's Server State in Named Volumes

## Context

[ADR 018][] makes OpenCode a client and a server, and [ADR 019][] runs the server
in one long-lived container that Paddock removes and recreates when it has stopped
or when the user changes its mounts. Whatever the server keeps in its container's
own filesystem is lost at that point.

Checked against OpenCode 2.3.0 in containers on 2026-11-17, running as root:

- The server writes its database, `opencode.db`, with its logs, under
  `/root/.local/share/opencode`, and creates `/root/.config/opencode` and
  `/root/.local/state/opencode`, the last of which stayed empty. The database
  holds sessions and the provider credentials a user signs in with, in plain
  text.
- The server writes its global settings, `opencode.json`, to its config directory
  when asked to add an MCP server or a plugin. A client cannot ask: with
  `--server`, `opencode mcp add` stops with "Unrecognized flag".
- The interactive client writes only interface state, under
  `/root/.local/state/opencode` (prompt history, and open tabs keyed by
  directory and holding the server's session IDs), and a log.
- Nothing stops two processes opening one database. That is what corrupted state
  in the reverted first attempt ([#53][]).
- An `opencode` started on the host without `--server` runs a background service
  of its own against the host's data directory.

The server also runs every tool, so its image is the environment the agent works
in, and Paddock builds no image a user has not asked for.

Some users will run OpenCode only through Paddock, yet want the host's install as a
fallback, for one, to work out why Paddock has stopped working, with the same
transcripts and sign-in on both sides.

## Options

### Option 1: Do nothing

The server and client keep their files in their containers' own filesystems.

**Pros:** Nothing to create or name.
**Cons:** Recreating the server, which adding a mount requires, discards every
session and the sign-in. The client loses its interface state on every run.
**Risks:** Users avoid recreating the server, and so avoid adding mounts.

### Option 2: Named volumes by default, the host's directories by opt-in (Accepted)

The server's data and state directories are two named volumes, and the client's
state directory a third. A user who mounts a host directory at one of the
server's two paths, under `agents.opencode.server.volumes`, gets that directory
there in place of the named volume.

**Pros:** State outlives the container. Only the one server ever opens the
database. The agent, whose shell can read the database, sees only credentials
entered for it.
**Cons:** By default a host OpenCode and Paddock's do not share sessions,
settings or sign-in, and the files are reachable only through Docker. A user
who opts in takes on Option 3's risks.
**Risks:** `docker volume prune -a` removes any that no container holds: the
client's whenever no client is running, and the server's between removing the
server and the next run. Without `-a` Docker leaves named volumes alone.

### Option 3: Always mount the host's OpenCode directories

As the `claude` agent mounts `~/.claude`: the host's `~/.local/share/opencode`
and its siblings, read-write, into the server.

**Pros:** One set of sessions, settings and sign-in for host and Paddock.
**Cons:** The paths differ by platform, and the host's database then carries
paths and state from a Linux container.
**Risks:** A host `opencode` run beside a Paddock server puts two processes on
one database, the fault #53 was reverted for, and nothing warns before it does.
The agent can read the host's credentials.

## Decision

Option 2. Option 3's risk is the one failure this work exists to remove, and it
would be reached by ordinary use: nothing about running `opencode` on the host
looks wrong. A default must not be corruptible by ordinary use.

**Sharing is the user's to choose.** A volume configured under
`agents.<name>.server.volumes` replaces the server's own volume at the same
container path, for any server. For OpenCode that is the opt-in: mount the
host's data directory at `/root/.local/share/opencode`, and the state directory
likewise. There is no setting that names the host's directories for the user;
they write the path, so what is shared is in their config in full. The docs
set out what they take on: the server is never stopped by Paddock, so a host
`opencode` started while it runs is a second process on the database, and the
user must stop one before starting the other; the agent can read every
credential in that database; and the database then holds container paths.
Paddock prints no warning for this yet: one shown on every run would be read
past, and it has no way to silence a single warning.

The volumes are named for the server, not the image, since there is one server:
`paddock-server-opencode-data` and `paddock-server-opencode-state`, at
`/root/.local/share/opencode` and `/root/.local/state/opencode`. The second is
precautionary: the server creates the directory and wrote nothing to it in
testing. The client's is `paddock-client-opencode-state`, at
`/root/.local/state/opencode`: one whatever the image, since what it holds
refers to the one server's sessions and not to the image.

**The config and cache directories get no volume.** The config directory holds
settings the agent itself can rewrite, MCP commands among them, so without a
volume its edits do not outlive the container. A user who wants settings there
mounts a host directory over the server's, read-only, under
`agents.opencode.server.volumes`; the client's copy of that directory is not
read.

**The server has no default image**, so `agents.opencode.server.image` is
required. OpenCode publishes one, `ghcr.io/anomalyco/opencode`, and the bundled
Dockerfile builds another; either as a default would start a server without the
user's toolchain, which the agent's first tool call would then discover. A
missing setting stops the run before anything starts.

## Consequences

- Sign-in happens once, through a Paddock-launched client, and survives the
  server being recreated. It does not carry over from a host install, short of
  OpenCode's own `auth export` and `auth import`.
- Removing the two server volumes resets OpenCode for every project. The docs
  name all three.
- Docker creates the volumes on first use, unlabelled, so Paddock cannot tell
  them from a volume of the same name made by something else, and would use it.
- A user who shares the data directory and runs a host `opencode` beside the
  server can corrupt the database, and nothing but the docs says so. A warning
  the user can silence is a [backlog item][suppressible warnings].
- Moving between the named volume and a host directory moves no data: sessions
  and sign-in stay where they were written.
- The server's container is shared and long-lived, so a setting the agent
  writes to the config directory in one project stays in force for every
  project until the server is recreated.
- Every project's client shares one state volume, so one project's prompt
  history is readable from another's client container. Each already holds the
  server's password.
- An image that runs as another user, or sets `XDG_DATA_HOME`, keeps its state
  outside the volumes, where recreating the server loses it.
- The volumes outlive the image. An OpenCode upgrade that migrates the database
  may leave an older image unable to open it.

[#53]: https://github.com/todofixthis/paddock/pull/53
[ADR 018]: 018-split-agents-into-clients-and-servers.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
[suppressible warnings]: ../future/suppressible-warnings.md
