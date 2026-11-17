# The `opencode` Agent

Runs [OpenCode](https://opencode.ai/) in two containers:

- **A server**, `paddock-server-opencode`, which runs every tool the agent uses: its
  shell commands and file edits happen there. paddock starts one on first use, and every
  project shares it from then on.
- **A client** per run, `paddock-<workdir name>-opencode`: the terminal interface, which
  connects to the server and is removed when you quit.

Because the tools run in the server, the server's image is your development environment
and the server's mounts decide what the agent can reach. Both are yours to set; paddock
supplies neither.

A run with this agent needs Docker Engine 25.0 or newer, client and daemon. An older one
stops it:

```
[docker] Agent servers need Docker Engine 25.0 or newer (API 1.44); found API 1.43
```

## Setting up

Build one image for both containers from the bundled Dockerfile, in a checkout of
[paddock](https://github.com/todofixthis/paddock):

```bash
docker build --build-arg AGENT=opencode -t paddock-opencode:latest -f images/Dockerfile .
```

Then, in your user config (`~/.config/paddock/config.toml`), choose the agent, name the
image for each container, and mount the directory that holds your projects into the
server:

```toml
agent = "opencode"
image = "paddock-opencode:latest"

[agents.opencode.server]
image = "paddock-opencode:latest"

[agents.opencode.server.volumes]
"~/code" = "/home/alice/code:rw"
```

Three things in the mount matter:

- **The container path equals the host path**, written in full and with symlinks
  resolved, as `pwd -P` prints it. `~` on the container side means `/root`, so
  `"~/code" = "~/code:rw"` mounts your projects at `/root/code`, which doesn't count.
- **`:rw` is written out.** A bare value mounts read-only.
- **It covers every project you run paddock in.** Mount the parent directory once rather
  than each project: a new mount takes effect only when the server is recreated, which
  ends every session in progress.

`paddock --dry-run`, from a project under `~/code`, checks all of this without starting
anything and prints the two commands a real run would execute, the server's then the
client's:

```
docker run -d --name paddock-server-opencode --network paddock-server-opencode … -p 127.0.0.1::4096 -e OPENCODE_DISABLE_AUTOUPDATE=1 -e OPENCODE_PASSWORD -e PADDOCK_SERVER_SECRET -v /home/alice/code:/home/alice/code:rw -v paddock-server-opencode-data:/root/.local/share/opencode:rw -v paddock-server-opencode-state:/root/.local/state/opencode:rw paddock-opencode:latest opencode serve --hostname 0.0.0.0 --port 4096
docker run --rm -it --name paddock-widgets-opencode --workdir=/home/alice/code/widgets -v /home/alice/code/widgets:/home/alice/code/widgets:rw -v paddock-client-opencode-state:/root/.local/state/opencode:rw --network paddock-server-opencode -e OPENCODE_DISABLE_AUTOUPDATE=1 -e OPENCODE_PASSWORD paddock-opencode:latest opencode --server http://paddock-server-opencode:4096
```

A variable printed without a value, such as `OPENCODE_PASSWORD`, is a secret paddock
passes through the environment so that it appears in no command.

The first real run prints the server's command, waits up to 30 seconds for the server
to answer, logs `Server: opencode (http://127.0.0.1:<port>)`, then opens OpenCode's
interface, not yet [signed in](#signing-in-and-where-state-lives). Later runs find the
server running and go straight to the interface.

`agents.opencode.server.image` is required: no default image carries your toolchain.
Without it the run stops:

```
[agents.opencode.server.image] No image is set, and server "opencode" has no default
```

The server's settings go in the global section of your user config and nowhere else;
[`agents.<name>.server`](../configuration.md#agentsnameserver) covers each one,
including having paddock build the server's image for you.

## What the agent can reach

The agent works in the server, so it sees a path only if the server mounts it. The
client's mounts, the workdir and your top-level
[`volumes`](../configuration.md#volumes), reach the interface and none of the tools:
list anything the agent needs, such as reference data, under
`[agents.opencode.server.volumes]` as well.

> [!CAUTION]
> **The agent can write to every project under the server's read-write mounts**
>
> Not only the project you started it in: every directory under those mounts, and each
> project's `.paddock/config.toml` with it. Granting
> [`project_toml`](../project-config.md#enabling-project-level-config) keys to a project
> under those mounts is therefore granting them to the agent, which can write that
> file. Mount only directories you would let the agent change, and grant `project_toml`
> to nothing beneath them that you would not grant the agent itself.

The workdir must sit under a read-write server mount, at the same path as on the host.
Where mounts nest, the most specific one covering the workdir is the one that counts.
Otherwise the run stops before anything starts, listing the mounts the server has:

```
[agent.server] Server "opencode" does not have /home/alice/work/api mounted read-write at the same path; its mounts: /home/alice/code:/home/alice/code:rw, paddock-server-opencode-data:/root/.local/share/opencode:rw, paddock-server-opencode-state:/root/.local/state/opencode:rw. Add a mount under [agents.opencode.server.volumes] in your user config, then recreate the server: docker rm -f paddock-server-opencode
```

The last clause appears when a server is running, since a container's mounts are fixed
when it is created. Add the mount, then run the printed command: it removes the server,
ending every project's sessions in progress, and the next paddock run starts a new one
with the new mounts. Saved sessions and your sign-in
[survive it](#signing-in-and-where-state-lives).

## Signing in and where state lives

Sign in once, from the client's interface. The credentials go to the server, so every
project is signed in from then on.

paddock keeps OpenCode's state in three named Docker volumes, apart from any OpenCode
on your host: by default the two share no sessions, settings or sign-in.

| Volume | Mounted in | At | Holds |
|---|---|---|---|
| `paddock-server-opencode-data` | the server | `/root/.local/share/opencode` | The database, `opencode.db`: sessions and your sign-in credentials, in plain text. Logs. |
| `paddock-server-opencode-state` | the server | `/root/.local/state/opencode` | Nothing, in testing against OpenCode 2.3.0. |
| `paddock-client-opencode-state` | every client | `/root/.local/state/opencode` | The interface's state: prompt history and open tabs, shared by every project. |

The volumes outlive the containers, so recreating the server loses neither sessions nor
sign-in. Two things do lose them:

- **`docker volume prune -a`** removes any of the three that no container holds: the
  client's whenever no client is running, the server's between removing the server and
  the next run. Without `-a`, Docker leaves named volumes alone.
- **An image that runs as another user, or sets `XDG_DATA_HOME`,** keeps its state
  outside these paths, in the container itself, where recreating the server discards
  it.

OpenCode's config directory, `/root/.config/opencode`, has no volume, so settings
written there last only as long as the server's container. To give the server settings
of your own, mount a host directory over it, read-only:

```toml
[agents.opencode.server.volumes]
"~/code" = "/home/alice/code:rw"
"~/.config/opencode" = "/root/.config/opencode"
```

Only the server's copy of that directory is read; mounting it into the client changes
nothing. A client cannot change the server's settings either: `opencode mcp add` fails
under `--server` with "Unrecognized flag".

## Sharing OpenCode's data with the host

Use this to keep OpenCode on your host as a fallback for paddock, with the same
sessions and sign-in on both sides. Read this whole section before you do: sharing is
safe only while you keep the two from running at once, and under rootful Docker on
Linux the host's OpenCode needs a `chown` before each use. Back the directory up first;
paddock cannot repair a corrupted database.

Find the host's data directory with `opencode debug paths` (the `data` row), then stop
the host's background service, which outlives OpenCode's window: `opencode service
stop`. Mount the directory read-write at exactly `/root/.local/share/opencode` in the
server:

```toml
[agents.opencode.server.volumes]
"~/code" = "/home/alice/code:rw"
"~/.local/share/opencode" = "/root/.local/share/opencode:rw"
```

- **Write `:rw`.** A bare value mounts the directory read-only.
- **Mount at that path, not above it.** A mount at exactly the path replaces paddock's
  named volume. One at a parent, such as `/root/.local/share`, replaces nothing: the
  named volume still mounts on top and hides your directory.
- **The host directory must exist.** If you have never run OpenCode on the host, the
  run stops:

  ```
  [agents.opencode.server.volumes.~/.local/share/opencode] Path '~/.local/share/opencode' does not exist or cannot be resolved (checked /home/alice/.local/share/opencode).
  ```

Only the data directory can be shared. The interface's state, prompt history and open
tabs, stays in the client's volume.

The mount takes effect when the server is next created. A server that is already
running keeps its named volume, and each run only [warns](#the-servers-lifecycle) that
its settings differ, until you run `docker rm -f paddock-server-opencode`. The new
server then shows the host's sessions and sign-in. Nothing is merged: what you did
under the named volume stays in the volume, and is what the server shows again if you
remove the mount and recreate it.

> [!CAUTION]
> **Two OpenCodes on one database can corrupt it**
>
> paddock never stops its server, and `opencode` on the host leaves a background
> service running after its window closes. Each opens the database, and nothing stops
> both doing so at once. Stop one before you start the other:
>
> - Before using OpenCode on the host: `docker stop paddock-server-opencode`. This ends
>   every project's sessions in progress.
> - Before the next paddock run with this agent, in any project:
>   `opencode service stop`. That run removes the stopped server and starts a new one.

Sharing has three further costs:

- **The agent can read every credential in the database**, not only those you entered
  through paddock: its shell runs in the server, where the file is mounted.
- **The database comes to hold paths from the container.** They match the host's for
  projects mounted at their own paths, which the server requires of every workdir.
- **Under rootful Docker on Linux, the server leaves root-owned files in the
  directory.** In testing the database came out owned by `root`, mode `600`, and
  `opencode` on the host, run as an ordinary user, then failed with
  `PermissionDenied … makeDirectory (…/opencode/log)`. Take the files back before using
  the host's:

  ```bash
  sudo chown -R "$(id -u):$(id -g)" ~/.local/share/opencode
  ```

## The client's image

The client's [`image`](../configuration.md#image) needs `opencode` on its `PATH` too,
though it runs none of the tools. A client whose OpenCode version differs from the
server's only warns, but one image for both, as [above](#setting-up), rules the
mismatch out.

With [`build.dockerfile`](../configuration.md#builddockerfile) set, paddock builds the
client's image with `AGENT=opencode`; the bundled Dockerfile installs OpenCode for that
value, at the version its `OPENCODE_VERSION` argument pins. That build runs after the
server has started, so it cannot supply the server's image on a first run: see
[`agents.<name>.server`](../configuration.md#agentsnameserver) for building that.

## The server's lifecycle

- **Started on first use.** The first run that finds no server creates the container,
  its network (also `paddock-server-opencode`) and its volumes, then waits up to 30
  seconds for OpenCode to answer before starting the client.
- **Never stopped by paddock.** It runs until you stop or remove it, or the Docker
  daemon stops. Quitting a client leaves it, and its sessions, running.
- **Shared by every project.** Later runs, from any workdir under its mounts, connect
  to the same server.
- **Recreated when found stopped.** A run that finds the container stopped removes it
  and creates a new one from your current settings. The volumes carry sessions and
  sign-in across.

Changed settings do not reach a running server. A run that finds its image, port or
mounts different from your config uses it as it is and warns:

```
Server "opencode" is running with settings that differ from your config; they apply when it is recreated: docker rm -f paddock-server-opencode
```

Run that command when you are ready to end every project's sessions in progress; the
next run applies your settings. A rebuilt image under an unchanged tag is not a
difference paddock sees, so recreate the server the same way to run it.

`docker logs paddock-server-opencode` shows the server's output. Read it before running
paddock again if the server failed to start: the next run removes a stopped container,
and its logs with it.

The server publishes port 4096 on your machine's loopback address only, at a port
Docker assigns; each run logs it as `Server: opencode (http://127.0.0.1:<port>)`. To
fix the port, set it and recreate the server:

```toml
[agents.opencode.server]
image = "paddock-opencode:latest"
port = 4096
```

The server demands a password, which paddock mints when it creates the container and
hands to each client.

## Arguments and commands

Arguments for every run go under `[agents.opencode]`, and one-off arguments after
`--`. Both follow the `--server` flag paddock adds:

```toml
[agents.opencode]
extra_args = ["--continue"]
```

`paddock` then runs `opencode --server http://paddock-server-opencode:4096 --continue`.
Without that setting, `paddock -- session list` runs
`opencode --server http://paddock-server-opencode:4096 session list`. Pass a prompt
with OpenCode's own flag, `paddock -- --prompt "fix it"`: OpenCode takes a bare
argument as a directory. See
[`agents.<name>.extra_args`](../configuration.md#agentsnameextra_args) for how sources
combine.

The client cannot run without its server. Choosing the client and switching the server
off, with `agent = { client = "opencode", server = false }` or `--agent-server=false`,
stops the run:

```
[agent] Agent "opencode" needs a server that speaks "opencode", but none is chosen; set agent.server
```

A paired run also joins the server's network, so a [`network`](../configuration.md#network)
of `bridge`, `default`, `host`, `none` or `container:…` stops it; name a network of
your own instead.

For every message a run with a server can stop with, see
[Agent servers](../configuration.md#agent-servers) under Troubleshooting in the
configuration reference.
