---
status: Accepted
date: 2026-11-16
scope: [docs/usage/, images/Dockerfile, src/paddock/__main__.py, src/paddock/agents/, src/paddock/config/, src/paddock/docker/]
summary: Paddock starts one long-lived container per server key (paddock-server-<key>) on demand and never stops it (not one per run, not stopped when the last client exits, and not left to the user to run); it runs without --rm, joins a Paddock-owned network, publishes its port on loopback only, carries a run-spec hash so drift warns rather than restarts, and holds its minted secret only in its environment, read back with docker inspect; agents.<name>.server settings are read only from the user config's global section, with absolute host paths checked only when that server is chosen; a server that runs tools in the project stops the run unless the workdir is mounted at its own path.
revisit-when: Paddock gains a command to manage servers; users need more than one instance of a server; a secret readable through docker inspect stops being acceptable; a server needs settings that vary by project; a companion container needs a per-run lifetime, as a proxy sidecar might; users need to connect to a server Paddock did not start.
---

# 019: Run One Shared Container per Agent Server

## Context

[ADR 018][] pairs a client with a server. Something must run the server. Paddock runs
exactly one kind of container today: `docker run --rm -it`, one per invocation, gone
when it exits.

A server differs in three ways. It is shared: every project's client connects to the
same one. It outlives any client. And an OpenCode server runs the agent's tools, so it
must have each project mounted at the project's own path; Docker cannot add a mount to
a running container.

Checked against OpenCode 2.3.0 in a container on 2026-11-16: the server is ready when
`GET /api/info` returns 200 with its password; it starts even with no password set,
minting one and printing it to its log; a request for a directory it does not have
mounted fails with 404, but the interactive client then falls back to the server's
own directory without saying so (read in the client's source, not run).

Paddock has no subcommands: a bare word after `paddock` replaces the agent's command
([ADR 007][]).

## Options

### Option 1: Do nothing

Each client container starts its own server.

**Pros:** Nothing new to manage.
**Cons:** Several servers share one state store, which is what corrupted OpenCode's.
**Risks:** None beyond the cons; this is the arrangement already reverted.

### Option 2: Paddock starts one container per server, on demand, and leaves it running (Accepted)

**Pros:** One server per state store by construction. The first run of any project
brings it up; later runs find it.
**Cons:** A container keeps running, and using resources, after the last client
exits. Nothing in Paddock stops it.
**Risks:** A server started under old settings keeps them until someone removes it.

### Option 3: Paddock stops the server when the last client exits

**Pros:** Nothing left running.
**Cons:** A host-run client is not a container, so Paddock cannot count clients
reliably; a crashed Paddock leaves the count wrong either way.
**Risks:** Stopping a server another terminal is still using.

### Option 4: The user runs the server; Paddock is given its address

**Pros:** No lifecycle in Paddock at all.
**Cons:** The user must reproduce by hand what makes the server usable: the image,
the secret, and every project mounted at its own path.
**Risks:** A wrong mount is silent with OpenCode: the agent works in another
directory.

## Decision

Option 2. Only Paddock knows the workdir, so only Paddock can check that the server
has it mounted before a client connects, and that check is what prevents an agent
silently working in the wrong directory. Leaving the server running costs resources
but never interrupts a session, where Option 3's guess could.

- **Identity.** One container per server key, named `paddock-server-<key>`. A
  concurrent Paddock that loses the race for the name treats the server as started.
- **No `--rm`.** A server that dies on start keeps its logs. A stopped container of
  that name is removed and recreated on the next run; state lives in volumes.
- **Never stopped or restarted by Paddock.** A label holds a hash of the run spec.
  On a mismatch Paddock warns, prints the `docker rm -f` command that recreates the
  server, and uses the running one: restarting would end other projects' sessions.
- **Network.** The server joins a Paddock-owned bridge network, `paddock`, as does a
  sandboxed client paired with it. Its port is published on `127.0.0.1` only, for
  host-run clients and for Paddock's readiness probe.
- **Secret.** Minted at start and held only in the container's environment; later
  runs read it back with `docker inspect`. The running container is the single
  source of truth, so there is no state file to lose and two racing first runs agree.
  It travels as `-e NAME`, never in a printed command. A server always gets one where
  its software supports it, since OpenCode would otherwise mint its own.
- **Settings.** `agents.<name>.server` (image, build, volumes, port) is read only
  from the global section of the user config; anywhere else it is a validation
  error. A shared server has no per-project settings, and an untrusted source must
  not widen its mounts. Its host paths must be absolute, an exception to
  [ADR 012][]: resolving them against the workdir would give one server a different
  run spec per project. They are checked on disk only when that server is chosen, in
  the spirit of [ADR 014][], so a stale server mount cannot stop a run that does not
  use it.
- **Workdir check.** A server that declares it runs tools in the project stops the
  run unless the workdir lies under one of its mounts at the same path, judged from
  the running container's mounts where it is running and from config where it is
  not.
- **No management flags.** A flag such as `--server-stop` would be deprecated as
  soon as subcommands exist (`docs/future/cli-subcommands.md`); until then the
  printed `docker rm -f` line is the interface.

## Consequences

- The container lifecycle is a class that knows nothing about agents, so a later
  companion container can reuse it.
- Anyone who can run `docker inspect` can read a server's secret. They can already
  run any container, so this grants nothing new.
- A project outside the server's mounts cannot use that server until the user adds
  a mount and recreates it, ending every session on it.
  `docs/future/server-mount-restart-offer.md` covers offering that.
- Changing a server's settings has no effect until the user recreates it; the drift
  warning says so on every run until they do.
- Everything mounted in a tool-running server is reachable from every session on it.
  Isolation between projects is then the set of mounts the user chose, not one
  project per container.

[ADR 007]: 007-split-agent-args-from-replacement-command.md
[ADR 012]: 012-resolve-relative-config-paths-against-the-workdir.md
[ADR 014]: 014-check-host-paths-only-in-the-matching-projects-entry.md
[ADR 018]: 018-split-agents-into-clients-and-servers.md
