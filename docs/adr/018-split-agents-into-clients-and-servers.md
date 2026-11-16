---
status: Accepted
date: 2026-11-16
scope: [README.rst, docs/usage/, pyproject.toml, src/paddock/__main__.py, src/paddock/agents/, src/paddock/cli.py, src/paddock/config/, src/paddock/docker/]
summary: An agent is a client (BaseAgent, the existing paddock.agents registry) optionally paired with a server (BaseServer, a new paddock.servers registry, authored under src/paddock/agents/); a client names its default server and the protocol it speaks, with no registry of named pairings and no server hooks on the agent class; agent is a client name, false, or a table naming either half; a string or false names the client and resets the server half to unnamed, and an unnamed half takes its default after the merge (client claude, server the merged client's default); agent stays one allowlist directive; a client is paired with a server only when both name the same protocol, so a client with a protocol needs such a server, and one without may be chosen beside any server but is not connected to it; servers are classes, not containers described in config; every client runs in a container, never on the host.
revisit-when: A pairing needs a name of its own, distinct from its client's; a client or server needs to speak more than one protocol; a client is shown to load and run nothing from the workdir and needs the host's terminal or tools; a server needs its connection arguments placed after extra_args; a run needs two servers at once.
---

# 018: Split Agents into Clients and Servers

## Context

An agent is one class, [`BaseAgent`][], that supplies the command, mounts and build
argument for one container per run. That fits an agent whose processes are
independent, such as Claude Code.

OpenCode and Omnigent are built around one server that every session shares. An
OpenCode agent written on the one-container model was reverted ([#53][]): each
container ran a full OpenCode process against the shared state database and corrupted
it.

The maintainer's stated goal: `agent` names a combination, `agent.client` and
`agent.server` override either half, novel combinations are allowed, and third
parties can add members through entry points.

Agents are already published through the `paddock.agents` entry-point group, and
[ADR 017][] keys per-agent settings by that registry's keys.

OpenCode's client runs none of the agent's tools; its server does. The first design
therefore ran that client on the host. Its source says otherwise about safety: the
terminal client loads plugins from `.opencode/plugins/` in the project it starts in
and in each parent directory, with no trust prompt found (read in OpenCode 2.3.0's
`tui/src/plugin/discovery.ts`, not run). The server has the project mounted
read-write, so the agent can write there.

## Options

Every option but the first needs something to keep a server container running;
[ADR 019][] decides that, and it does not rank these.

### Option 1: Do nothing

**Pros:** No change.
**Cons:** A server-based agent can only be run one server per container, the
arrangement that corrupted OpenCode's state.
**Risks:** Users run such agents unsandboxed instead.

### Option 2: Clients keep the agent class; servers get their own (Accepted)

`BaseAgent` and its registry become the client half. A new `BaseServer`, in a new
`paddock.servers` entry-point registry, is the server half. A client names its
default server and the protocol it speaks.

**Pros:** An agent written against today's `BaseAgent` keeps working unchanged.
**Cons:** The class called "agent" is the client, while config says `agent.client`.
**Risks:** A pairing cannot have a name of its own; `agent = "x"` always means client
`x`.

### Option 3: One agent class with optional server hooks

**Pros:** The smallest change; one registry.
**Cons:** `agent.client` and `agent.server` would each take half of an agent, so every
agent must tolerate being used for one half only.
**Risks:** A server with no client of its own needs a dummy agent.

### Option 4: `agent` names a pairing, held in its own registry

A pairing names a client and a server; `agent = "x"` looks up pairing `x`.

**Pros:** A pairing can be named apart from its client.
**Cons:** Every agent needs a pairing registered before `agent` can name it, or
`agent` must consult two registries in a fixed order.
**Risks:** A published agent and a later pairing of the same name silently change
what `agent = "x"` means.

### Option 5: Servers defined in config, not as classes

Config describes a long-lived container; an agent declares which it needs.

**Pros:** Any companion container fits without a class.
**Cons:** A container described in config cannot know its own readiness check, secret
or mount requirements, which are what make a server usable.
**Risks:** Rebuilds docker-compose inside Paddock.

## Decision

Option 2. It gives the two halves the maintainer asked for as separately registered
classes, so adding a client or a server is one new class, and it leaves the existing
entry-point group alone. A registry of pairings can be added in
front of it later without undoing this; nothing needs one yet, since `extra_args`
covers the case raised, choosing the harness an Omnigent client launches.

**Clients.** `BaseAgent` gains class attributes whose defaults preserve today's
behaviour, `DEFAULT_SERVER` (none) and `PROTOCOL` (none), and two methods a paired
client overrides to receive the server's address and secret.

**Every client runs in a container.** That includes OpenCode's, despite it running no
tools, because it loads plugins from the workdir. Its container reaches the server
over a Docker network.

**The `agent` value.** Each half is unnamed, named, or `false`: the shell for the
client, none for the server. A string names the client and resets the server to
unnamed; `false` does the same with the shell. A table names the halves it lists.
Sources merge half by half, so a table overrides only what it names, while a string
or `false` discards a server a lower source named. After the merge, an unnamed client
is `claude` and an unnamed server is the merged client's `DEFAULT_SERVER`. So
`agent.client` alone brings that client's server with it, and no source needs the
registry to be read. `--agent-client`, `--agent-server` and the matching
`PADDOCK_AGENT_*` variables name one half. Within one source the string applies
first, reset included, and then that source's halves; the environment source must
handle this explicitly, its name-to-path mapping losing the string otherwise.

`agent` stays one allowlist directive ([ADR 004][]): a grant of half the value could
not carry the reset.

**Pairing.** A client is paired with a server when both name the same `PROTOCOL`. A
client with a `PROTOCOL` must be paired, and the run stops otherwise. A client
without one may be chosen beside any server: the server is started, but the client
neither joins its network nor receives its secret, and ADR 019's checks on a paired
run do not apply. So
`{client = "claude", server = "omnigent"}` runs and does not route Claude through
Omnigent. This is the "novel combinations" allowance.

**Names.** A chosen client or server that is not installed stops the run, after the
merge, as an unknown agent does today. This extends ADR 017's `agents.<name>` to
servers' keys, judged per setting: `extra_args` needs a client of that name and
`server` a server of that name, and either without one draws ADR 017's warning.

## Consequences

- A third party adds a server by registering a `BaseServer` subclass under
  `paddock.servers`; no Paddock module changes.
- An OpenCode run is two containers, the shared server and a client, and the client's
  image needs OpenCode installed at a version the server accepts. An image without
  it fails when the client starts, after the server is already up.
- A source granted `agent` can now name a server, which starts a long-lived
  container with the user's own server settings. The docs say so where they weigh
  what each grant hands a project file.
- `agent` may now be a table, so the filter that rejects one accepts a table whose
  keys are `client` and `server`.
- Choosing a no-protocol client beside a server starts a container that client never
  uses. The log says so.
- One server per run rules out a server that every client shares alongside its own,
  as a proxy would be; that needs its own decision.

[#53]: https://github.com/todofixthis/paddock/pull/53
[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 017]: 017-configure-agents-in-an-agents-table.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
[`BaseAgent`]: ../../src/paddock/agents/__init__.py
