# Agent Clients and Centralised Servers

Design for running agents that coordinate through one shared server, starting with
OpenCode and then Omnigent. Agreed with Phoenix on 2026-11-15. Items marked
**(call)** are the author's decisions, not Phoenix's; challenge them at review.

## Intent

Paddock runs one independent agent process per container. That suits Claude Code and
fails for agents built around a single server:

- **OpenCode** was added and reverted (`4496c82`). Each container ran a full OpenCode
  process against the shared state database and corrupted it. OpenCode also expects to
  reach every project from one server, and Docker cannot add a mount to a running
  container.
- **Omnigent** coordinates harnesses (Claude Code, Codex, OpenCode and others) through
  one server that hosts dial into.

Supporting both widens what Paddock can sandbox. The same machinery, a long-lived
container Paddock keeps running, is what the HTTP proxy sidecar
(`docs/future/squid-proxy-sidecar.md`) needs later.

## Goals

- `agent` names a client and its default server. `agent.client` and `agent.server`
  override either half.
- One server container per server type, shared by every project.
- Per-agent settings, including `extra_args` appended to the agent's command.
- OpenCode works end to end: server in a container, client on the host.
- Omnigent works end to end, after a spike settles the unknowns below.
- Third-party packages add clients and servers through entry points, with no edits to
  Paddock.

## Non-goals

- The proxy sidecar itself.
- Commands to manage servers (`paddock service`), and `setup`, `doctor` and `run`.
  Backlog: `docs/future/cli-subcommands.md`.
- Offering to restart a server with a new mount. Backlog:
  `docs/future/server-mount-restart-offer.md`.
- Removing an inherited `extra_args` entry.
- Server-management flags. They would be deprecated when `paddock service` lands.

## Anti-goals

- Two server processes sharing one state directory, under any configuration.
- An agent silently working in a directory other than the workdir.
- A project-level or untrusted config source changing what the shared server mounts.
- A file the agent can write choosing, or passing arguments to, a process on the host.
- Secrets in a printed command line.

## What the research found

Sources: `anomalyco/opencode` v2.3.0 and `omnigent-ai/omnigent` 0.23.0.dev0, read on
2026-11-15. Check against the installed versions before relying on a detail.

### OpenCode

- `opencode serve --hostname H --port P` starts the server. A client connects with
  `--server <url>`; there is no environment variable for the URL.
- A password is mandatory: `OPENCODE_PASSWORD` on both sides, HTTP Basic, username
  `opencode`.
- `GET /api/info` needs auth and returns 200 once ready, 503 while starting.
- The client sends its cwd per request. The directory must exist **in the server** at
  the same absolute path. If it does not, the client silently falls back to the
  server's default directory.
- Every tool (shell, edits, LSP) runs in the server.
- State is SQLite (WAL) at `$XDG_DATA_HOME/opencode/opencode.db`, credentials
  included. Nothing stops two processes opening it.
- Without `--server`, a host `opencode` starts its own background service on the
  host's data directory.
- Install: `npm install -g @opencode/cli`. Official image:
  `ghcr.io/anomalyco/opencode:<version>` (Alpine, versioned tags only).

**Checked against a running server** (2.3.0, in a container, 2026-11-16):

- With `OPENCODE_PASSWORD` set, `GET /api/info` returned 200 within two seconds of
  start; no credentials or a wrong password returned 401.
- **Without `OPENCODE_PASSWORD` the server still starts**: it mints a password and
  prints it to its log. Paddock must therefore always set one, or it cannot connect.
- A request naming a mounted directory (`x-opencode-directory`) returned that
  project; an unmounted one returned 404 `LocationNotFoundError`; no header fell back
  to the server's cwd.
- A second container reached the server by container name over a user-defined
  network, with `opencode session list --server http://<name>:4096`. Without the
  password the client stopped with "requires a password; set OPENCODE_PASSWORD".
- The password is readable from `docker inspect` (`.Config.Env`).
- The `@opencode/cli-linux-x64` npm package is a single glibc binary that runs on the
  e2e base image as copied in.

Not checked: the interactive client's silent fallback when its directory is missing,
and anything needing a model.

### Omnigent

- The server coordinates only; it relays no inference. `omnigent server`, default port
  6767; the Docker image `ghcr.io/omnigent-ai/omnigent-server` listens on 8000 and
  serves `GET /health` without auth.
- A harness is launched by Omnigent, never connected to it. `omnigent claude --server
  <url>` starts a host daemon, which starts a runner, which runs `claude` in tmux and
  attaches the terminal. A plain `claude` cannot use an Omnigent server.
- Only the client side needs the project directory and the model credentials.
- A non-loopback server defaults to account login. `OMNIGENT_AUTH_ENABLED=0` makes
  every caller the same user.
- State defaults to SQLite under `OMNIGENT_DATA_DIR`. One server per database.
- Install: PyPI `omnigent` (Python 3.12+), plus tmux, git and, on Linux, `bwrap`.

## Approaches

**A. Separate client and server classes (chosen).** Clients and servers are separate
registered classes. Each names the protocol it speaks, so a mismatched pair fails
clearly. Container lifecycle sits in its own class for the proxy sidecar to reuse.
Chosen because it matches `agent.client` / `agent.server` directly and keeps "new
member = new class only".

**B. One agent class with optional server hooks.** Smaller diff, but mixing halves
means taking part of one agent and part of another, and the proxy (a server with no
client) becomes an agent with a dummy client.

**C. A general services layer.** `[services.x]` defines any long-lived container.
The proxy drops in for free, but it rebuilds docker-compose, and a config-defined
service cannot know its own readiness check or auth.

**Deviation from A as first described (call).** A was pitched with a third registry of
named pairings. This design drops it: a client declares its `DEFAULT_SERVER`, and
`agent = "x"` means "client `x` with its default server". The existing
`paddock.agents` entry-point group then stays the client registry, so agents that
third parties already ship keep working, and there is one registry fewer. The cost: a
pairing cannot have a name of its own (`claude-via-omnigent`). `extra_args` covers the
only case raised so far.

## Design

### Configuration

Choosing and configuring are separate keys, because TOML cannot hold `agent = "x"`
and `[agent.x]` in one scope.

```toml
# Choose: a client name, false, or a table naming either half.
agent = "omnigent"
# agent = { client = "claude", server = "omnigent" }

# Configure an agent, whether or not it is chosen.
[agents.omnigent]
extra_args = ["claude"]

[agents.opencode.server]
image = "my-dev-image"

[agents.opencode.server.volumes]
"/Users/phx/Dev" = "/Users/phx/Dev:rw"

[projects."/Users/phx/Dev/phx-claude-siat".agents.claude]
extra_args = ["--plugin-dir=./"]
```

#### `agent`

- A string names a client and takes that client's `DEFAULT_SERVER` (possibly none).
  `false` is the shell client with no server, as today.
- A table sets only the halves it names. `server = false` means no server.
- Merging: each source's value is normalised to `{client, server}` first (a string
  expands to both halves; a table stays partial), then sources deep-merge in weight
  order. So user-level `agent = "claude"` with project-level `agent.server =
  "omnigent"` gives client `claude`, server `omnigent`; a higher source's string
  replaces both halves. "No server" must be stored as `false`, not `None`:
  `DropEmpty` strips `None`, and a lower source's server would survive the merge.
- After merging, Paddock checks the pair (see Pairing) and stops on a mismatch.
- **(call)** `--agent-client` / `--agent-server` and `PADDOCK_AGENT_CLIENT` /
  `PADDOCK_AGENT_SERVER` exist for parity with `--agent` / `PADDOCK_AGENT`. Within one
  source, a half overrides the same source's string.

#### `agents.<name>`

`<name>` is a client's or server's registry key. A name nothing installed has draws a
warning after the merge and its settings are ignored (ADR 017): a validation error
would stop every run on a machine missing a plugin that a shared config names.

- `extra_args`: list of strings, for client `<name>`. Appended after the client's
  command and before the tokens after `--`. It never reaches Paddock's own flags:
  `extra_args = ["--agent=plan"]` behaves as `paddock -- --agent=plan`. Ignored when
  a replacement command is given, as agent args are (ADR 007). A higher source's list
  replaces a lower one's. No environment-variable form, as for `volumes`.
- `server`: settings for server `<name>`.
  - `image`: overrides the server class's default image.
  - `build`: same shape and meaning as top-level `build`, applied to the server's
    image, with the server class's build args.
  - `volumes`: same shape as top-level `volumes`.
  - `port`: host port to publish on `127.0.0.1`. Unset, Docker assigns one **(call)**.

  **(call)** Host paths under `server` must be absolute after `~` expansion; a
  relative one is a validation error. Resolving against the workdir (ADR 012) would
  give the shared server a different run spec per project. They are checked on disk
  only when that server is chosen, in the spirit of ADR 014, so a stale server mount
  cannot break a Claude run. The config ADR records both as exceptions.

**(call)** `agents.<name>.server` is read only from the global section of the user
config. In a `[projects]` entry, the project file, the environment or the CLI it is a
validation error. A shared server has no per-project configuration, and an untrusted
source must not widen its mounts.

`agents` joins `CONFIG_FIELDS` as an allowlist directive, so an untrusted source needs
`agents` allowlisted to set `extra_args`.

**(call)** The project file can never choose a client that runs on the host, nor set
`extra_args` for one, whatever the allowlist says; either is a validation error. An
OpenCode server mounts its roots read-write, so the agent can write any project's
`.paddock/config.toml`, and those values would become a host process and its
arguments. For the same reason `config.project_dir_readonly` protects nothing under
a server's mounts; the OpenCode page says so in a `CAUTION` alert.

#### `image`

Top-level `image` stays required only when the chosen client runs in a container.

### Clients

`BaseAgent` keeps its name, its registry (`agent_registry`, entry-point group
`paddock.agents`) and its current methods. It is the client half. It gains:

- `DEFAULT_SERVER: ClassVar[str | None] = None`. The server `agent = "<key>"` selects.
- `PROTOCOL: ClassVar[str | None] = None`. The server protocol it speaks; `None` for
  a client that needs no server.
- `SANDBOXED: ClassVar[bool] = True`. `False` runs the client on the host.
- `get_server_args(connection) -> list[str]`, default `[]`. Inserted after the
  command and before `extra_args`.
- `get_server_env(connection) -> dict[str, str]`, default `{}`.

Existing subclasses need no change.

### Servers

A new `BaseServer` in a new `EntryPointClassRegistry`, group `paddock.servers`, from
`phx-class-registry`, with instantiation through the registry as for agents.

- `SERVER_KEY`, `PROTOCOL`.
- `DEFAULT_IMAGE: ClassVar[str | None]`. `None` makes
  `agents.<name>.server.image` required.
- `CONTAINER_PORT`.
- `REQUIRES_WORKDIR_MOUNT: ClassVar[bool] = False`. `True` for a server that runs
  tools in the project.
- `get_command()`, `get_volumes()`, `get_scratch_volumes()`, `get_build_args()`, as
  for clients.
- `get_env(secret) -> dict[str, str]`.
- `is_ready(connection) -> bool`. An HTTP probe from the host through the published
  port.
- `GENERATES_SECRET: ClassVar[bool]`. Whether Paddock mints a shared secret.

`ServerConnection` is what a server hands a client: the URL from the host
(`http://127.0.0.1:<published port>`), the URL from a container
(`http://paddock-server-<key>:<container port>`), the secret or `None`, and the
network name.

### Pairing

Checked once, before anything is created:

- `client.PROTOCOL` set: a server must be chosen and its `PROTOCOL` must match.
- `client.PROTOCOL` is `None`: any server, or none, is allowed. The server still
  starts and a sandboxed client still joins its network, but the client does not
  connect to it; Paddock logs that. Phoenix asked that novel combinations be allowed.
  This also fits the proxy sidecar, a server every client uses without speaking a
  protocol.
- `REQUIRES_WORKDIR_MOUNT` and the server is **already running**: the workdir must lie
  under a mount of the running container (read with `docker inspect`, not from
  config) whose container path equals its host path. Otherwise stop, naming the
  mounted roots and the `docker rm -f` line that recreates the server. Not yet
  running: check the configured volumes the same way.

Each failure names both halves and what to change.

So `agent = { client = "claude", server = "omnigent" }` runs, but does **not** route
Claude through Omnigent: `claude` has no protocol. `agent = "omnigent"` with
`extra_args = ["claude"]` does. Among the built-in classes the useful mixed pair is
the shell client with a server, for debugging.

### Server lifecycle

`ManagedContainer` (under `src/paddock/docker/`) owns "make sure this container is
running" and knows nothing about agents, so the proxy sidecar can reuse it.

- **Name:** `paddock-server-<SERVER_KEY>`. One per Docker daemon.
- **Start on demand.** Not running: prepare the image under the server's `build`
  policy, then `docker run -d`. A name conflict from a concurrent Paddock counts
  as started. Then poll `is_ready` for up to 30 seconds; on timeout, or if the container
  exits first, stop with a pointer to `docker logs` and leave the container.
- **No `--rm`**, so a server that dies on start keeps its logs. A stopped container
  of that name is removed and recreated on the next run; state lives in volumes, so
  nothing is lost.
- **Never stopped by Paddock.**
- **Drift.** The container carries a label holding a hash of its run spec (image,
  command, volumes, environment names, port). Running with a different hash: warn,
  print `docker rm -f paddock-server-<key>`, and carry on with the running server.
- **Network.** A Paddock-owned bridge network, `paddock`, created on demand. The
  server joins it. A sandboxed client paired with a server joins it too, in addition
  to any configured `network`.
- **Port.** `CONTAINER_PORT` is published on `127.0.0.1` only, read back with
  `docker port`. Paddock logs the URL on each run.
- **Secret (call).** Minted when the server starts and held nowhere but the
  container's environment. Later runs read it back with `docker inspect`. The running
  container is then the only source of truth: no state file to lose, and two racing
  first runs both read the winner's secret. Passed as `-e NAME` with the value in the
  subprocess environment, never in argv.
- **`--dry-run`** prints the server's `docker run` line when the server is not
  running, starts nothing and mints nothing. Where the client's command needs a port
  Docker has not yet assigned, it prints `<port>` in its place.

### Running the client

- **Sandboxed:** as today, plus the `paddock` network, `get_server_env` passed as
  `-e NAME`, and the command `[*get_command(), *get_server_args(), *extra_args,
  *agent_args]`.
- **On the host:** Paddock runs the same command directly, with cwd at the workdir.
  No image, volumes, network or `.paddock` directory are involved. A missing binary
  stops the run with an install hint. A replacement command is an error **(call)**:
  there is no sandbox to run it in.

### OpenCode

- **Client `opencode`:** `SANDBOXED = False`, `DEFAULT_SERVER = "opencode"`, command
  `opencode`, server args `--server <host URL>`, server env `OPENCODE_PASSWORD`.
- **Server `opencode`:** command `opencode serve --hostname 0.0.0.0 --port 4096`;
  `REQUIRES_WORKDIR_MOUNT = True`; `GENERATES_SECRET = True`; ready when
  `GET /api/info` with Basic auth returns 200; build arg `AGENT=opencode`;
  `OPENCODE_DISABLE_AUTOUPDATE=1`.
- **Image (call):** `DEFAULT_IMAGE = None`. Tools run in the server, so its image is
  the user's development environment and the official Alpine image would mislead.
  The docs show the bundled Dockerfile with `AGENT=opencode`.
- **State (call):** data and state directories are named Docker volumes, never the
  host's `~/.local/share/opencode`. A host `opencode` run without Paddock starts its
  own service there, which would again put two processes on one database. Sign-in
  happens through the Paddock-launched client. The host's
  `$XDG_CONFIG_HOME/opencode` is mounted read-only when it exists.
- **Bundled Dockerfile:** an `opencode` case installing `@opencode/cli` at a
  Renovate-pinned version, with its README row and CI smoke test (ADR 016).

### Omnigent (provisional)

Built after a throwaway spike. Intended shape:

- **Client `omnigent`:** sandboxed, `DEFAULT_SERVER = "omnigent"`, command
  `omnigent`. The harness is the first `extra_args` entry (`["claude"]`). It mounts
  what that harness needs to sign in.
- **Server `omnigent`:** the published server image, pinned; SQLite in a named
  volume; ready on `GET /health`.

The spike must answer:

1. **Auth.** With auth off, any container on the `paddock` network can drive the
   server, and the server can launch runners in other projects' sandboxes. That
   breaks isolation between projects, so auth-off is acceptable only if the spike
   shows the server unreachable from other sandboxes. OpenCode differs: its user
   opts in to shared reach by naming the roots, which Phoenix accepted; a sandboxed
   Omnigent client still promises one project per container. Otherwise: how does a client
   container get a token without an interactive login each run?
2. **`bwrap`.** Does Omnigent's Linux sandbox run in an unprivileged container, or
   can it be disabled by config?
3. **Terminal.** Does `omnigent claude` attach correctly under `docker run -it`?
4. **Connection.** Does `OMNIGENT_SERVER` reach `omnigent claude`, or must
   `--server` follow the subcommand? The latter needs server args placed after
   `extra_args`, which changes `get_server_args`.

If the spike shows the shape is wrong, it comes back as a design change, not a patch.

### Documentation

- One page per agent under `docs/usage/agents/`, since their configuration diverges.
  `configuration.md` keeps the shared keys and links out.
- ADRs before implementation (`phx:writing-adrs`): one for the `agent` / `agents`
  config shape, one for the client/server split and managed containers.
- `docs/future/squid-proxy-sidecar.md` gains a pointer to `ManagedContainer` and the
  `paddock` network.

## Delivery

Three pull requests, each with its own plan:

1. **`agents.<name>` and `extra_args`.** No server concepts.
2. **Client/server architecture and OpenCode.**
3. **Omnigent**, after the spike.

End-to-end checks use the `e2e-testing` skill. In a cloud session only
`mcr.microsoft.com` images pull, so the OpenCode check builds its server image from
the skill's base image with the `@opencode/cli` binary copied in.

## Left to the builder

- Where normalising `agent` sits in the loader, and how the `Agent` filter changes.
- The exact run-spec fields hashed for drift.
- Two `--network` flags on `docker run` work on Docker 29 (checked 2026-11-15). On an
  older Docker that rejects them, `docker network connect` after start.
- Container paths for OpenCode's volumes.
