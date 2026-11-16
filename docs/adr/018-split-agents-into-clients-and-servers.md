---
status: Accepted
date: 2026-11-16
scope: [README.rst, docs/usage/, pyproject.toml, src/paddock/__main__.py, src/paddock/agents/, src/paddock/cli.py, src/paddock/config/, src/paddock/docker/]
summary: An agent is a client (BaseAgent, the existing paddock.agents registry) optionally paired with a server (BaseServer, a new paddock.servers registry); a client names its default server and the protocol it speaks, with no registry of named pairings and no server hooks on the agent class; agent is a client name, false, or a table naming either half, normalised to client and server before sources merge; a client with a protocol needs a server speaking it, and one without may run beside any server; a client may run on the host, unsandboxed, and the project file can never choose such a client or set its extra_args; image is required only for a sandboxed client.
revisit-when: A pairing needs a name of its own, distinct from its client's; a client or server needs to speak more than one protocol; a host-run client needs a replacement command; a server needs its connection arguments placed after extra_args; a second untrusted config source appears beside the project file.
---

# 018: Split Agents into Clients and Servers

## Context

An agent is one class, [`BaseAgent`][], that supplies the command, mounts and build
argument for one container per run. That fits an agent whose processes are
independent, such as Claude Code.

OpenCode and Omnigent are built around one server that every session shares. An
OpenCode agent written on the one-container model was reverted ([#53][]): each
container ran a full OpenCode process against the shared state database and corrupted
it. OpenCode's client holds no project state and runs no tools; its server does both.
Omnigent's client launches the harness and does need a sandbox.

The maintainer's stated goal: `agent` names a combination, `agent.client` and
`agent.server` override either half, novel combinations are allowed, and third
parties can add members through entry points.

Agents are already published through the `paddock.agents` entry-point group, and
[ADR 017][] keys per-agent settings by that registry's keys.

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
**Risks:** A server that has no client, as a proxy would be, needs a dummy agent.

### Option 4: A third registry of named pairings

`agent = "x"` looks up a pairing that names a client and a server.

**Pros:** A pairing can be named apart from its client.
**Cons:** `paddock.agents` already holds agent classes, so either that group changes
meaning and breaks published agents, or `agent` stops reading from it.
**Risks:** Three registries to keep consistent for a need nobody has raised.

### Option 5: A general services layer

Config defines any long-lived container; agents declare the services they need.

**Pros:** Any companion container fits.
**Cons:** A service defined in config cannot know its own readiness check, secret or
mount requirements, which are what make a server usable.
**Risks:** Rebuilds docker-compose inside Paddock.

## Decision

Option 2. It gives the two halves the maintainer asked for as separately registered
classes, so adding a client or a server is one new class, and it leaves the existing
entry-point group and ADR 017's keys alone. Option 4's named pairings are deferred
until one is needed: `extra_args` already covers the case raised, choosing the harness
an Omnigent client launches.

**Clients.** `BaseAgent` gains class attributes, each with a default that preserves
today's behaviour: `DEFAULT_SERVER` (none), `PROTOCOL` (none) and `SANDBOXED` (true),
and two methods a paired client overrides to pass the server's address and secret.

**The `agent` value.** A string names a client and takes its `DEFAULT_SERVER`; `false`
is the shell with no server; a table names either half, and `server = false` means
none. Each source's value is normalised to a client and a server before sources
merge, so a table in a higher source overrides only the half it names and a string
overrides both. `--agent-client`, `--agent-server` and the matching `PADDOCK_AGENT_*`
variables set one half.

**Pairing.** A client with a `PROTOCOL` needs a server with the same one, and stops
the run otherwise. A client without one may run beside any server or none: the server
starts and the client joins its network, but nothing connects them. So
`{client = "claude", server = "omnigent"}` runs and does not route Claude through
Omnigent. This is the "novel combinations" allowance, and it is also how a server
that every client uses without a protocol, such as a proxy, would fit.

**Host-run clients.** A client with `SANDBOXED = False` runs on the host, as
OpenCode's does. It has no container, so `image` is required only for a sandboxed
client, and a replacement command is an error, there being no sandbox to run it in.

**The project file cannot choose a host-run client, nor set `extra_args` for one.**
Such a value is dropped with a warning, whatever the allowlist grants ([ADR 004][]).
A server may mount many projects read-write, so an agent working in one can write
another's `.paddock/config.toml`; honouring those keys would turn a file the agent can
write into a process on the host and its arguments.

## Consequences

- A third party adds a server by registering a `BaseServer` subclass under
  `paddock.servers`; no Paddock module changes.
- `config.project_dir_readonly` protects nothing under a server's read-write mounts.
  The docs for such a server say so.
- A project that wants a host-run agent for everyone cannot say so in its committed
  file; each user sets it in their own `[projects]` entry.
- `agent` may now be a table, so the filter that rejects a table there
  ([ADR 017][]'s companion change) accepts one with the keys `client` and `server`.
- Names are checked after the merge, as today: an unknown client or server stops the
  run only when it is the one chosen.

[#53]: https://github.com/todofixthis/paddock/pull/53
[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 017]: 017-configure-agents-in-an-agents-table.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
[`BaseAgent`]: ../../src/paddock/agents/__init__.py
