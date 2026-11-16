---
status: Accepted
date: 2026-11-16
scope: [docs/usage/, images/Dockerfile, src/paddock/__main__.py, src/paddock/agents/, src/paddock/cli.py, src/paddock/config/, src/paddock/docker/]
summary: Paddock starts one long-lived container per server key (paddock-server-<key>, identified by label) on demand and never stops or restarts it, with no flag to manage it (not one per run or per project, not stopped when the last client exits, and not left to the user to run); it runs without --rm and without a restart policy, a stopped one being removed and recreated on the next run; it has a Paddock-owned network of its own, publishes its port on loopback only, carries its run spec in labels so drift warns rather than restarts, and holds its minted secret only in its environment, read back with docker inspect; agents.<name>.server settings are read only from the user config's global section, with absolute host paths checked only when that server is chosen; a server that runs tools in the project stops a paired client's run unless the workdir lies under a read-write mount at its own path; the project file is still honoured under a server's mounts, as the allowlist grants.
revisit-when: Paddock gains a command to manage servers; users need more than one instance of a server; idle servers' resource use draws complaints; recreating a server to add a mount proves too disruptive, or Docker gains a way to add a mount to a running container; a secret readable through docker inspect stops being acceptable; a server needs settings that vary by project; a companion container needs a per-run lifetime, as a proxy sidecar might; users need to connect to a server Paddock did not start; the Docker daemon is not on the local machine; an agent is found to have rewritten a project file or the user config through a server's mounts.
---

# 019: Run One Shared Container per Agent Server

## Context

[ADR 018][] pairs a client with a server. Something must run the server. Paddock runs
exactly one kind of container today: `docker run --rm -it`, one per invocation, gone
when it exits.

A server differs in three ways. It is shared: the maintainer's requirement is one
server that every project's client connects to. It outlives any client. And an
OpenCode server runs the agent's tools, so it must have each project mounted at the
project's own path; Docker cannot add a mount to a running container.

Checked against OpenCode 2.3.0 in a container on 2026-11-16: the server is ready when
`GET /api/info` returns 200 with its password; it starts even with no password set,
minting one and printing it to its log; a request for a directory it does not have
mounted fails with 404, and the interactive client then falls back to the server's
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
**Risks:** A server started under old settings keeps them until it is next created.

### Option 3: Paddock stops the server when the last client exits

**Pros:** Nothing left running.
**Cons:** Paddock must count clients across terminals, and a crashed Paddock leaves
the count wrong.
**Risks:** Stopping a server another terminal is still using.

### Option 4: The user runs the server; Paddock is given its address

**Pros:** No lifecycle in Paddock at all.
**Cons:** The user must reproduce by hand what makes the server usable: the image,
the secret, and every project mounted at its own path.
**Risks:** A wrong mount is silent with OpenCode: the agent works in another
directory.

### Option 5: One server per project

Paddock starts a server for each workdir, with its own state.

**Pros:** No mount to add later, and nothing shared between projects.
**Cons:** Contradicts the maintainer's requirement of one server for all projects,
which is how OpenCode is meant to be used; credentials live in the state store, so
each project signs in separately.
**Risks:** As many idle containers as projects.

## Decision

Option 2. Only Paddock knows the workdir, so only Paddock can check that the server
has it mounted before a client connects, and that check is what prevents an agent
silently working in the wrong directory. Leaving the server running costs resources
but never interrupts a session, where Option 3's guess could.

- **Identity.** One container per server key, named `paddock-server-<key>` and
  carrying a label that names the key. A container with that name and no such label
  stops the run. A concurrent Paddock that loses the race for the name treats the
  server as started.
- **No `--rm`, no restart policy.** A server that dies on start keeps its logs until
  the next run, which removes a stopped container by the ID it observed, without
  force, and recreates it under the current settings. A failed removal means another
  Paddock got there first. So settings take effect whenever the server is next
  created, a reboot included.
- **Never stopped or restarted by Paddock.** Labels hold the run spec. On a mismatch
  with config Paddock warns, prints the `docker rm -f` command that recreates the
  server, and uses the running one: restarting would end other projects' sessions.
- **Network.** Each server has its own Paddock-owned bridge network, identified by
  label, which a paired client's container joins alongside any configured `network`.
  One network for all servers would let a sandbox paired with one reach another. A
  configured `network` that cannot be combined with a second (`host`, `none`,
  `container:`) stops a paired run. The port is also published on `127.0.0.1` only,
  for Paddock's readiness probe and a server's own web interface.
- **Secret.** Always minted at start and held only in the container's environment;
  later runs read it back with `docker inspect`. The running container is the single
  source of truth, so there is no state file to lose and two racing first runs agree.
  It travels as `-e NAME`, never in a printed command. Leaving it unset would not
  mean no secret with OpenCode, which mints its own.
- **Settings.** `agents.<name>.server` (image, build, volumes, port) is read only
  from the global section of the user config. In a `[projects]` entry it is a
  validation error, that being the user's own file; in the project file it is
  dropped with a warning, as a key that source may not set ([ADR 004][]), so a
  committed file cannot stop the runs of everyone who granted it something else. A
  shared server has no per-project settings, and an untrusted source must not widen
  its mounts. Its host paths must be absolute, an exception to [ADR 012][]:
  resolving them against the workdir would give one server a different run spec per
  project. They are checked on disk only when that server is chosen, in the spirit
  of [ADR 014][], so a stale server mount cannot stop a run that does not use it.
- **Workdir check.** A server that declares it runs tools in the project stops a
  paired client's run unless the most specific of its mounts covering the workdir
  is read-write and maps to the same path. A running server is judged by the mounts
  recorded in its labels, not by config and not by Docker's own report of them,
  which Docker Desktop may rewrite.
- **`--dry-run`** prints the server's `docker run` line where one would be needed
  and creates, builds and removes nothing.
- **No management flags.** A flag such as `--server-stop` would be deprecated as
  soon as subcommands exist (`docs/future/cli-subcommands.md`); until then the
  printed `docker rm -f` line is the interface.
- **The project file and the user config are honoured as before.** Everything under
  a tool-running server's read-write mounts is writable by the agent, including each
  project's `.paddock/config.toml` and, if the user mounts it, the user config. The
  maintainer's decision is to keep the allowlist as the control: the project file is
  opt-in, the user chooses the grant, and the docs state the risk. Paddock neither
  ignores the project file under such a mount nor refuses a mount that contains the
  user config.

## Consequences

- The container lifecycle is a class that knows nothing about agents, so a later
  companion container can reuse it.
- Anyone who can run `docker inspect` can read a server's secret. They can already
  run any container, so this grants nothing new.
- A project outside the server's mounts cannot use that server until the user adds
  a mount and recreates it, ending every session on it.
  `docs/future/server-mount-restart-offer.md` covers offering that.
- Under a tool-running server, a `project_toml` grant for a mounted project is in
  effect a grant to the agent, and `config.project_dir_readonly` protects nothing
  there: an agent can write a project file that the user's next run in that project
  obeys, a `volumes` entry mounting the host among them. The docs carry this as a
  caution, and the planned `doctor` command is to flag `project_toml = true`.
- Isolation between projects under such a server is the set of mounts the user
  chose, not one project per container.

[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 007]: 007-split-agent-args-from-replacement-command.md
[ADR 012]: 012-resolve-relative-config-paths-against-the-workdir.md
[ADR 014]: 014-check-host-paths-only-in-the-matching-projects-entry.md
[ADR 018]: 018-split-agents-into-clients-and-servers.md
