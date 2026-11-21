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
- OpenCode works end to end: a shared server container and a sandboxed client.
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
- Any agent process running on the host. Every client is sandboxed.
- Secrets in a printed command line.

## What the research found

Sources: `anomalyco/opencode` v2.3.0 and `omnigent-ai/omnigent` 0.23.0.dev0, read on
2026-11-15. Check against the installed versions before relying on a detail.

### OpenCode

- `opencode serve --hostname H --port P` starts the server. A client connects with
  `--server <url>`; there is no environment variable for the URL.
- Every request needs the password: `OPENCODE_PASSWORD` on both sides, HTTP Basic,
  username `opencode`. A server started without one mints its own (see below).
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

ADRs 017, 018 and 019 are the binding record. This section was revised on 2026-11-16
to match 018 and 019, after their review and a source check showed that OpenCode's
client loads plugins from the workdir, so it cannot run on the host.

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

- A string names a client; `false` is the shell; a table names either half, and
  `server = false` means none.
- Sources merge half by half: a table overrides only the halves it names, and a
  string sets the client and clears any server a lower source named. After the
  merge, an unnamed client is `claude` and an unnamed server is the merged client's
  `DEFAULT_SERVER`. So `agent.client` alone brings that client's server with it,
  and no source reads the registry.
- "Server cleared" and "no server" must both survive `DropEmpty`, which strips
  `None`; they need distinct stored values.
- `--agent-client` / `--agent-server` and `PADDOCK_AGENT_CLIENT` /
  `PADDOCK_AGENT_SERVER` set one half. Within one source, a half overrides that
  source's own string; the environment source needs explicit handling for this,
  since its name-to-path mapping otherwise loses the string.
- After merging, Paddock checks the pair (see Pairing).

#### `agents.<name>`

`<name>` is a client's or server's registry key, known if either registry has it. A
name nothing installed has draws a warning after the merge and its settings are
ignored (ADR 017): a validation error
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

`agents.<name>.server` is read only from the global section of the user config. In a
`[projects]` entry it is a validation error; in the project file it is dropped with a
warning (ADR 019). It has no environment or CLI form.

`agents` is an allowlist directive, so an untrusted source needs it allowlisted to
set `extra_args`.

### Clients

`BaseAgent` keeps its name, its registry (`agent_registry`, entry-point group
`paddock.agents`) and its current methods. It is the client half. Every client runs
in a container. It gains:

- `DEFAULT_SERVER: ClassVar[str | None] = None`.
- `PROTOCOL: ClassVar[str | None] = None`. The server protocol it speaks; `None` for
  a client that needs no server.
- `get_server_args(connection) -> list[str]`, default `[]`. Inserted after the
  command and before `extra_args`.
- `get_server_env(connection) -> Mapping[str, str | Secret]`, default `{}`.

Existing subclasses need no change.

### Servers

A new `BaseServer`, authored under `src/paddock/agents/`, in a new
`EntryPointClassRegistry` (group `paddock.servers`) from `phx-class-registry`, with
instantiation through the registry as for agents.

- `SERVER_KEY`, `PROTOCOL`.
- `DEFAULT_IMAGE: ClassVar[str | None]`. `None` makes
  `agents.<name>.server.image` required.
- `CONTAINER_PORT`.
- `REQUIRES_WORKDIR_MOUNT: ClassVar[bool] = False`. `True` for a server that runs
  tools in the project.
- `get_command()`, `get_volumes()`, `get_scratch_volumes()`, `get_build_args()`, as
  for clients.
- `get_env(secret) -> Mapping[str, str | Secret]`.
- `is_ready(connection) -> bool`. An HTTP probe from the host through the published
  port.

`ServerConnection` is what a server hands a client: the URL from a container on the
server's network (`http://paddock-server-<key>:<container port>`), the URL from the
host (`http://127.0.0.1:<published port>`), the secret, and the network name.

### Pairing

Checked once, before anything is created (ADR 018):

- `client.PROTOCOL` set: a server must be chosen and its `PROTOCOL` must match.
- `client.PROTOCOL` is `None`: any server, or none. A chosen server is started, but
  the client neither joins its network nor gets its secret, and the workdir check
  below is skipped. Paddock logs that the two are not connected.
- A paired client and a server with `REQUIRES_WORKDIR_MOUNT`: the most specific
  server mount covering the workdir must be read-write and map to the same path.
  Otherwise stop, naming the mounted roots and the `docker rm -f` line that
  recreates the server.

### Server lifecycle

`ManagedContainer` (under `src/paddock/docker/`) owns "make sure this container is
running" and knows nothing about agents. ADR 019 states the rules; in outline:

- **Identity:** `paddock-server-<SERVER_KEY>`, confirmed by a label.
- **Start on demand:** prepare the image under the server's `build` policy, create
  the server's network, `docker run -d`, then poll `is_ready` for up to 30 seconds.
  On timeout, or if the container exits first, stop with a pointer to
  `docker logs` and leave the container; one created but never started is removed.
- **No `--rm`, no restart policy.** A stopped server is removed by ID, without
  force, and recreated on the next run.
- **Never stopped by Paddock.** Labels hold the run spec, mounts included. Drift
  warns and prints `docker rm -f paddock-server-<key>`.
- **Network:** one Paddock-owned, labelled bridge network per server. A paired
  client joins it alongside any configured `network`; `bridge`, `default`,
  `host`, `none` and `container:` stop a paired run.
- **Port:** `CONTAINER_PORT` is published on `127.0.0.1` only (Docker-assigned
  unless `port` is set), for the readiness probe and the server's web interface.
- **Secret:** always minted at start, held only in the container's environment, read
  back with `docker inspect`.
- **Environment variables:** a safe one is passed as `-e NAME=value` and shows in
  the printed command; a secret one, being any value that contains the secret or
  is wrapped in `Secret`, is passed as `-e NAME` (ADR 019).
- **`--dry-run`** prints the server's `docker run` line where one is needed and
  creates, builds and removes nothing; an unassigned port prints as `<port>`.

### Running the client

As today, plus, for a paired client: the server's network, `get_server_env` passed
as `-e` flags by the same rule, and the command `[*get_command(), *get_server_args(), *extra_args,
*agent_args]`. A replacement command works as it does for any client.

### OpenCode

- **Client `opencode`:** `DEFAULT_SERVER = "opencode"`, `PROTOCOL = "opencode"`,
  command `opencode`, server args `--server <container URL>`, server env
  `OPENCODE_PASSWORD`, build arg `AGENT=opencode`.
- **Server `opencode`:** command `opencode serve --hostname 0.0.0.0 --port 4096`;
  `REQUIRES_WORKDIR_MOUNT = True`; ready when `GET /api/info` with Basic auth
  returns 200; build arg `AGENT=opencode`; `OPENCODE_DISABLE_AUTOUPDATE=1`.
- **Server image (call):** `DEFAULT_IMAGE = None`. Tools run in the server, so its
  image is the user's development environment. The client's image (top-level
  `image`) needs OpenCode too; the docs recommend one image for both, since a
  version mismatch only warns.
- **State (call):** by default the server's data and state directories are named
  Docker volumes, not the host's `~/.local/share/opencode`: a host `opencode` run
  without Paddock starts its own service there, which would again put two processes
  on one database. Sign-in happens through the Paddock-launched client. A user may
  share the host's data directory by opt-in (ADR 021).
- **Bundled Dockerfile:** `images/opencode.Dockerfile` (ADR 022) installing `@opencode/cli` at a
  Renovate-pinned version, with its README row and CI smoke test (ADR 016).
- **Docs:** a `CAUTION` that everything under the server's read-write mounts is
  writable by the agent, project files included, so a `project_toml` grant there is
  a grant to the agent (ADR 019).

### Omnigent (provisional)

Built after a throwaway spike. Intended shape:

- **Client `omnigent`:** `DEFAULT_SERVER = "omnigent"`, `PROTOCOL = "omnigent"`, command
  `omnigent`. The harness is the first `extra_args` entry (`["claude"]`). It mounts
  what that harness needs to sign in.
- **Server `omnigent`:** the published server image, pinned; SQLite in a named
  volume; ready on `GET /health`.

The spike must answer:

1. **Auth.** Each server has its own network, so only Omnigent's own clients can
   reach it. But every project's client is on that network, and the server can
   launch runners in any of them. With auth off, one project's sandbox could
   therefore drive another's. Can a client container get a token without an
   interactive login each run?
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
- ADRs: 017 (the `agents` table), 018 (clients and servers) and 019 (the shared
  server container).
- `docs/future/squid-proxy-sidecar.md` gains a pointer to `ManagedContainer` and to
  ADR 018's note that a server every client shares needs its own decision.

## Delivery

Six pull requests, each with its own plan. The work was split further as its size
became clear, to keep the config rules, the Docker lifecycle and each agent apart:

1. **`agents.<name>` and `extra_args`.** No server concepts. Merged.
2. **Agent halves and pairing.** `agent` as a client and a server half, the server
   registry, server settings and the pairing check. No Docker changes; a run that
   chooses a server stops until the server container lands. Merged.
3. **Discards for the project file.** Merged.
4. **The server container.** `ManagedContainer`, the launcher and the paired run.
   Merged.
5. **OpenCode.** Its client and server, its bundled Dockerfile and the user
   docs. Delivered by the pull request that adds ADR 021.
6. **Omnigent**, after the spike.

End-to-end checks use the `e2e-testing` skill. In a cloud session only
`mcr.microsoft.com` images pull, so the OpenCode check builds its server image from
the skill's base image with the `@opencode/cli` binary copied in.

## Left to the builder

- Where normalising `agent` sits in the loader, and how the `Agent` filter changes.
- The exact run-spec fields hashed for drift.
- Two `--network` flags on `docker run` work on Docker 29 (checked 2026-11-15). A
  Docker older than 25.0 rejects them, and stops a run that chooses a server
  (ADR 019).
- Container paths for OpenCode's volumes, and what, if anything, the client
  container persists (prompt history, preferences).
