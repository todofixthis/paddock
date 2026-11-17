# Configuration Reference

Every setting paddock reads, where to set it, and how sources combine. For the trust
model behind the project-level file, see
[Project-Level Config and the Allowlist](project-config.md).

## Where configuration comes from

paddock merges five sources. Each sets the same [directives](#directives), except
where the [reference table](#reference-table) says otherwise. Sources merge in
ascending weight; on conflict, the higher weight wins, per key as [Precedence](#precedence)
describes.

| Weight | Source | Where | Notes |
|---|---|---|---|
| 10 | `project_toml` | `<workdir>/.paddock/config.toml` | Committed with a project. Ignored until you [enable it](project-config.md#enabling-project-level-config). |
| 20 | `user` | `$XDG_CONFIG_HOME/paddock/config.toml` | Your defaults for every project. `~/.config` stands in for `XDG_CONFIG_HOME` when unset, empty or relative. |
| 30 | `project_overrides` | `[projects."<workdir>"]` in the user file | Your settings for one project; see [`projects`](#projects). |
| 50 | `env` | `PADDOCK_*` environment variables | |
| 60 | `cli` | Command-line flags | |

`<workdir>` is the directory paddock mounts as the workspace: the current directory, or
[`--workdir`](#run-options). Every file is optional, but some source must supply
[`image`](#image).

> [!NOTE]
> **Setting `XDG_CONFIG_HOME` with a config already in `~/.config`**
>
> If `XDG_CONFIG_HOME` points somewhere other than `~/.config` and has no
> `paddock/config.toml`, paddock reads `~/.config/paddock/config.toml` instead, with a
> warning to move it; that fallback goes in paddock 2.0. When both files exist, paddock
> reads the XDG one and warns that the other is ignored. So move an existing file rather
> than starting a new one.

### Precedence

The project file has the lowest weight, so it can't override a value you set, but its
[`volumes`](#volumes) and [`build.args`](#buildargs) still add to yours, and its
[`agents`](#agentsnameextra_args) settings apply to any agent you have set none for
(see below).
[Precedence](project-config.md#precedence) on the project-config page walks through an
example.

Merging is per key, not per source:

- **Single values** (`image`, `network`, `build.policy` …): the highest-weight source
  that sets one wins.
- **`agent`**: merges half by half when written as a table, so one source can name the
  client and another the server; see [`agent`](#agent).
- **`[agents]`**: merges per agent name, so sources can each configure a different
  agent. An agent's `extra_args` list is replaced whole by the highest-weight source
  that sets it, never joined. An agent's [`server`](#agentsnameserver) settings have
  one source, your user file's global section, so they never merge.
- **`[build]`**: each key merges separately, and `build.args` merges per argument
  name. A per-project `build.policy` keeps your user-level `build.dockerfile`.
- **`[volumes]`**: merge per host path. Sources add mounts; a higher-weight source can
  change the container path or mode of a host path a lower one mounts, but not remove
  it.

Higher sources cannot unset a value, with two exceptions: an empty
[`network`](#network) falls back to Docker's default network, and an empty
[`extra_args`](#agentsnameextra_args) clears the list.

### Validation

paddock validates every enabled source before merging, then the merged result. Any
error stops the run before Docker starts, naming the source and key:

```
[user:build.dockerfile] Path 'images/Dockerfile' does not exist or cannot be resolved (checked /home/alice/code/widgets/images/Dockerfile).
```

`final` in place of a source name means the merged config is incomplete, e.g.
`[final:image] Non-empty value expected.` when no source sets `image`. A source
blocked by the [allowlist](#configallowlist) can't stop a run: its errors become a
warning. A partly allowed source is validated in full, so a bad value in a key the
allowlist would drop still stops the run.

Path values (`build.context`, `build.dockerfile` and the host side of `volumes`) must
exist when paddock starts. paddock expands a leading `~` to your home directory and
follows symlinks. A relative path resolves against the workdir, whichever source sets
it: `.paddock/config.toml` (not `.paddock/` itself), the user file, the environment and
the command line. A value therefore means the same thing in every source and wherever
you run paddock from: `"data"` names `<workdir>/data`, and `"../widgets-api"` a sibling
of the project. The workdir here is its real path, with symlinks resolved, so `..`
climbs from a symlinked checkout's target, not the link. A path error gives the value
as written, then the path paddock checked.

A relative path you set once for every project, in the global section of your user
file, an exported `PADDOCK_*` variable or a shell alias, therefore names a different
directory in each project, and stops any run in a project that lacks it. Use an
absolute or `~` path for anything that lives in one place, such as a Dockerfile beside
your user file, and put a mount only some projects have in their
[`projects`](#projects) entries.

paddock checks every [`projects`](#projects) entry's keys and values on each run, but
checks paths only in the entry for this workdir. Another project's entry can't stop this
run by naming a path that has gone, such as after that project moved.

Paths under [`agents.<name>.server`](#agentsnameserver) follow two rules of their own.
They must be absolute or start with `~`, since every project shares the server, and
paddock checks that they exist only on a run that chooses that server.

## Reference table

🚫 marks a source that can't set the directive. A key shown without a table header goes
above the file's first `[table]` header: placed below one, it becomes part of that
table. A key shown under a header goes in that table; if your file already has the
header, add the key there rather than repeating the header, which TOML rejects.
`<workdir>` is the workdir's absolute path, with symlinks resolved and no `~`; see
[`projects`](#projects).

<table class="docutils align-default paddock-reference">
<thead>
<tr>
<th>Directive</th>
<th><code>config.toml</code> (user)</th>
<th>Per-project override (user <code>config.toml</code>)</th>
<th><code>.paddock/config.toml</code></th>
<th>Environment</th>
<th>Command line</th>
</tr>
</thead>
<tbody>
<tr>
<td>

[`agent`](#agent)

</td>
<td>

```toml
agent = "claude"
```

</td>
<td>

```toml
[projects."<workdir>"]
agent = "claude"
```

</td>
<td>

```toml
agent = "claude"
```

</td>
<td>

```shell
PADDOCK_AGENT=claude
```

</td>
<td>

```shell
--agent=claude
```

</td>
</tr>
<tr>
<td>

[`agent.client`](#agent)

</td>
<td>

```toml
[agent]
client = "opencode"
```

</td>
<td>

```toml
[projects."<workdir>".agent]
client = "opencode"
```

</td>
<td>

```toml
[agent]
client = "opencode"
```

</td>
<td>

```shell
PADDOCK_AGENT_CLIENT=opencode
```

</td>
<td>

```shell
--agent-client=opencode
```

</td>
</tr>
<tr>
<td>

[`agent.server`](#agent)

</td>
<td>

```toml
[agent]
server = "opencode"
```

</td>
<td>

```toml
[projects."<workdir>".agent]
server = "opencode"
```

</td>
<td>

```toml
[agent]
server = "opencode"
```

</td>
<td>

```shell
PADDOCK_AGENT_SERVER=opencode
```

</td>
<td>

```shell
--agent-server=opencode
```

</td>
</tr>
<tr>
<td>

[`agents.<name>.extra_args`](#agentsnameextra_args)

</td>
<td>

```toml
[agents.claude]
extra_args = ["--verbose"]
```

</td>
<td>

```toml
[projects."<workdir>".agents.claude]
extra_args = ["--verbose"]
```

</td>
<td>

```toml
[agents.claude]
extra_args = ["--verbose"]
```

</td>
<td>

🚫

</td>
<td>

🚫

</td>
</tr>
<tr>
<td>

[`agents.<name>.server`](#agentsnameserver)

</td>
<td>

```toml
[agents.opencode.server]
image = "paddock-opencode:latest"
port = 4096

[agents.opencode.server.build]
dockerfile = "~/src/images/Dockerfile"

[agents.opencode.server.volumes]
"~/code" = "/home/alice/code:rw"
```

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
</tr>
<tr>
<td>

[`build.args`](#buildargs)

</td>
<td>

```toml
[build.args]
NODE_VERSION = "24"
```

</td>
<td>

```toml
[projects."<workdir>".build.args]
NODE_VERSION = "24"
```

</td>
<td>

```toml
[build.args]
NODE_VERSION = "24"
```

</td>
<td>

🚫

</td>
<td>

```shell
--build-args-NODE_VERSION=24
```

</td>
</tr>
<tr>
<td>

[`build.context`](#buildcontext)

</td>
<td>

```toml
[build]
context = "~/src/images"
```

</td>
<td>

```toml
[projects."<workdir>".build]
context = "~/src/images"
```

</td>
<td>

```toml
[build]
context = "~/src/images"
```

</td>
<td>

```shell
PADDOCK_BUILD_CONTEXT=~/src/images
```

</td>
<td>

```shell
--build-context=~/src/images
```

</td>
</tr>
<tr>
<td>

[`build.dockerfile`](#builddockerfile)

</td>
<td>

```toml
[build]
dockerfile = "~/src/images/Dockerfile"
```

</td>
<td>

```toml
[projects."<workdir>".build]
dockerfile = "~/src/images/Dockerfile"
```

</td>
<td>

```toml
[build]
dockerfile = "~/src/images/Dockerfile"
```

</td>
<td>

```shell
PADDOCK_BUILD_DOCKERFILE=~/src/images/Dockerfile
```

</td>
<td>

```shell
--build-dockerfile=~/src/images/Dockerfile
```

</td>
</tr>
<tr>
<td>

[`build.policy`](#buildpolicy)

</td>
<td>

```toml
[build]
policy = "daily"
```

</td>
<td>

```toml
[projects."<workdir>".build]
policy = "daily"
```

</td>
<td>

```toml
[build]
policy = "daily"
```

</td>
<td>

```shell
PADDOCK_BUILD_POLICY=daily
```

</td>
<td>

```shell
--build-policy=daily
```

</td>
</tr>
<tr>
<td>

[`config.allowlist`](#configallowlist)

</td>
<td>

```toml
[config.allowlist]
project_toml = ["volumes"]
```

</td>
<td>

```toml
[projects."<workdir>".config.allowlist]
project_toml = ["volumes"]
```

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
</tr>
<tr>
<td>

[`config.project_dir_readonly`](#configproject_dir_readonly)

</td>
<td>

```toml
[config]
project_dir_readonly = false
```

</td>
<td>

```toml
[projects."<workdir>".config]
project_dir_readonly = false
```

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
</tr>
<tr>
<td>

[`image`](#image)

</td>
<td>

```toml
image = "paddock-claude:latest"
```

</td>
<td>

```toml
[projects."<workdir>"]
image = "paddock-claude:latest"
```

</td>
<td>

```toml
image = "paddock-claude:latest"
```

</td>
<td>

```shell
PADDOCK_IMAGE=paddock-claude:latest
```

</td>
<td>

```shell
--image=paddock-claude:latest
```

</td>
</tr>
<tr>
<td>

[`network`](#network)

</td>
<td>

```toml
network = "dev-services"
```

</td>
<td>

```toml
[projects."<workdir>"]
network = "dev-services"
```

</td>
<td>

```toml
network = "dev-services"
```

</td>
<td>

```shell
PADDOCK_NETWORK=dev-services
```

</td>
<td>

```shell
--network=dev-services
```

</td>
</tr>
<tr>
<td>

[`projects`](#projects)

</td>
<td>

```toml
[projects."/home/alice/code/widgets"]
image = "widgets-dev:latest"
```

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
<td>

🚫

</td>
</tr>
<tr>
<td>

[`volumes`](#volumes)

</td>
<td>

```toml
[volumes]
"~/datasets" = "/data:ro"
```

</td>
<td>

```toml
[projects."<workdir>".volumes]
"~/datasets" = "/data:ro"
```

</td>
<td>

```toml
[volumes]
"~/datasets" = "/data:ro"
```

</td>
<td>

🚫

</td>
<td>

```shell
--volume=~/datasets:/data:ro
```

</td>
</tr>
</tbody>
</table>

### Run options

These control a single run rather than the container's configuration. Each has one
source, takes no part in merging, and ignores the allowlist.

| Option | Command line | Effect |
|---|---|---|
| Agent arguments | `paddock -- --continue` | Everything after `--` is appended to the agent's command, after any [`extra_args`](#agentsnameextra_args): `claude --continue`. |
| Command | `paddock /bin/bash` | The first positional argument, and everything after it, replaces the agent's command. Put paddock flags first. |
| Dry run | `--dry-run` | Prints the `docker run` command, and an [agent server](#agentsnameserver)'s if the run would start one, and exits 0 without building, pulling, creating or running anything. |
| Help | `--help` | Prints usage and exits. |
| Quiet | `--quiet` | Suppresses logging, warnings and the printed `docker run` commands. Errors still print. |
| Version | `--version` | Prints the paddock version and exits. |
| Workdir | `--workdir=PATH` | Mounts `PATH` as the workspace instead of the current directory. paddock resolves it to an absolute real path first, and that path is the key [`projects`](#projects) matches. |

A prompt needs `--` in front of it: `paddock "fix this bug"` tries to execute a command
named `fix this bug`. Flags before `--` must be spelt in full; paddock rejects
abbreviations and unknown flags. paddock exits with the container's exit status,
Docker's when a build or pull fails, 1 on a config error and 2 on an unknown flag.

## Directives

### `agent`

The coding agent to run in the container, or `false` for a plain bash shell.

- **Type:** agent name (string), `false`, or a table naming `client`, `server` or both
- **Default:** `"claude"`
- **TOML:** `agent = "claude"`, or `agent = false` (the string `"false"` also works);
  as a table, `agent = { client = "opencode", server = "opencode" }`
- **Environment:** `PADDOCK_AGENT=claude`; for one half, `PADDOCK_AGENT_CLIENT` or
  `PADDOCK_AGENT_SERVER`
- **Command line:** `--agent=claude`; for one half, `--agent-client` or `--agent-server`
- **Allowlist path:** `agent`, which covers both halves

Each bundled agent has a page of its own:

| `agent` | Runs | Server | Page |
|---|---|---|---|
| `"claude"` | Claude Code: `claude` | none | [The `claude` Agent](agents/claude.md) |
| `false` | A shell: `/bin/bash`, with no extra mounts | none | this section |
| `"opencode"` | OpenCode's client: `opencode --server …` | `opencode` | [The `opencode` Agent](agents/opencode.md) |

The agent decides the command, any extra mounts, the `AGENT` build argument passed when
paddock [builds the image](#builddockerfile) (`none` for `false`), and the container
name, `paddock-<workdir name>-<agent>`.

Installed packages can add agents; see
[Adding agents](https://phx-paddock.readthedocs.io/en/latest/#adding-agents). An unknown
name stops the run and lists the installed agents:

```
[agent] Unknown agent "claud"; installed agents: claude, false, opencode
```

Use `false` to explore an image or debug it. With [`build.dockerfile`](#builddockerfile)
set, though, a rebuild under `false` tags the same [`image`](#image) with `AGENT=none`,
replacing an image that had the agent installed. To get a shell in your agent's image,
pass a [command](#run-options) instead: `paddock /bin/bash`. For an agent with a
server that is a shell in the client's container; the tools run in the server, which
`docker exec -it paddock-server-<name> /bin/bash` reaches.

#### Clients and servers

An agent has two halves. The **client** is what runs in the container paddock starts
for each run. The **server**, for an agent that has one, is a long-lived container
every project shares, configured under [`agents.<name>.server`](#agentsnameserver).
`claude` and `false` are clients with no server.

A name on its own chooses a client and brings that client's default server with it:
`agent = "opencode"` chooses the `opencode` client and the `opencode` server. That is
all most configs need. The table form names a half on its own:

| Half | TOML | Environment | Command line | Value |
|---|---|---|---|---|
| Client | `agent = { client = "opencode" }` | `PADDOCK_AGENT_CLIENT=opencode` | `--agent-client=opencode` | An agent name, or `false` for the shell |
| Server | `agent = { server = "opencode" }` | `PADDOCK_AGENT_SERVER=opencode` | `--agent-server=opencode` | A server name, or `false` for none |

A table may be written inline, as above, or under an `[agent]` header. An empty
`PADDOCK_AGENT`, `PADDOCK_AGENT_CLIENT` or `PADDOCK_AGENT_SERVER` stops the run.

Sources merge the two halves separately, the higher weight winning each:

- **A half named alone leaves the other as lower sources set it.** With
  `agent = "opencode"` in your user file, `--agent-server=false` keeps the `opencode`
  client and switches its server off, which stops the run, since that client needs
  its server.
- **A whole value names the client and resets the server**, discarding one a lower
  source named. `--agent=claude` over a user file's
  `agent = { client = "opencode", server = "opencode" }` runs `claude` with no server.
- **A server no source names is the default of the client the merge ends up with**,
  not of a client that lost. `--agent-client=claude` over `agent = "opencode"` runs
  `claude` with no server.
- **Within one source, the whole value applies first and the halves over it**, whatever
  order you write them in: `--agent-server=opencode --agent=false` is the shell beside
  the `opencode` server. Only the command line and the environment can hold both; a
  TOML file sets `agent` to a name or to a table, and one with `agent = "claude"`
  cannot also have an `[agent]` header.

A client that needs a server stops the run when it has none, or one of another kind:

```
[agent] Agent "opencode" needs a server that speaks "opencode", but none is chosen; set agent.server
```

A server chosen beside a client that does not use it, as in the last example above, is
still started, and paddock logs that the two are not connected.

### `agents.<name>.extra_args`

Arguments paddock adds to an agent's command on every run, so you don't retype them
after `--`.

- **Type:** list of strings
- **Default:** none
- **TOML:** `extra_args = ["--verbose"]` under `[agents.claude]`; the table is
  `agents`, plural, and `[agent.claude]` is an error
- **Environment:** none. A `PADDOCK_AGENTS_…` variable stops paddock with an error
- **Command line:** none; pass one-off arguments [after `--`](#run-options)
- **Allowlist path:** `agents`, which covers every agent's settings

`<name>` is the agent the arguments belong to, spelt as [`agent`](#agent) spells it;
use `false`, in lower case, for the shell. Settings stay in place while another agent is chosen, so a
per-project `agent`, or `--agent`, switches agents without passing one agent's flags
to another.

The arguments follow the agent's command and come before anything after `--`. With

```toml
[agents.claude]
extra_args = ["--verbose"]
```

`paddock -- "fix it"` runs `claude --verbose "fix it"`. They never reach paddock's own
flags: `extra_args = ["--quiet"]` passes `--quiet` to the agent. A
[command](#run-options) that replaces the agent's drops them, along with the agent's
command.

Because your arguments come first, don't end the list with an option whose value is
optional, such as Claude Code's `--resume`: the agent would take the first thing after
`--`, your prompt, as that option's value.

Each string is one argument, passed as written: paddock expands no `~` and resolves no
path, and a path names a location in the container. A relative one works because the
workdir is mounted at the same path:

```toml
[projects."/Users/alice/code/my-plugin".agents.claude]
extra_args = ["--plugin-dir=./"]
```

A higher-weight source replaces the whole list. To add one argument for a project,
repeat the ones you still want; to drop them all, set an empty list:

```toml
[projects."/Users/alice/code/widgets".agents.claude]
extra_args = []
```

Nothing on the command line drops them for a single run, short of replacing the
command: `paddock claude "fix it"`.

Under [project-level config](project-config.md#the-allowlist), a project file granted
`agents` can set arguments for any agent whose `extra_args` you have not set yourself.

Settings for a name no installed agent has are ignored with a
[warning](#troubleshooting), so a config shared between machines still works where an
agent's package is missing. Check the spelling if you see it unexpectedly.

### `agents.<name>.server`

Settings for an agent's server: the long-lived container every project's client
connects to. Of the bundled agents only [`opencode`](agents/opencode.md) has one, and
its page is the place to start.

- **Type:** table with keys `build`, `image`, `port` and `volumes`
- **Default:** none
- **TOML:** under `[agents.opencode.server]`, in the global section of your user file
  only
- **Environment:** none. A `PADDOCK_AGENTS_…` variable stops paddock with an error
- **Command line:** none
- **Allowlist path:** none — no other source may set it

`<name>` is the server's name, as the server half of [`agent`](#agent) spells it.

| Key | Type | Default | Effect |
|---|---|---|---|
| `build` | table: `args`, `context`, `dockerfile`, `policy` | none | Builds or pulls `image` when paddock creates the server's container. The keys work as the top-level [`build.args`](#buildargs), [`build.context`](#buildcontext), [`build.dockerfile`](#builddockerfile) and [`build.policy`](#buildpolicy) do, and a build gets the server's own `AGENT` argument (`opencode` for `opencode`). |
| `image` | non-empty string | the server's own, if it has one; `opencode` has none | The image the server runs. Separate from the top-level [`image`](#image), which the client runs. |
| `port` | integer, 1 to 65535 | a free port Docker picks | The port on your machine's loopback address (`127.0.0.1`) the server is published on. |
| `volumes` | table, host path to container path with an optional `:ro` or `:rw` mode | none | Host directories or files mounted into the server. Values work as the top-level [`volumes`](#volumes) do: a bare value is read-only, and `~` in the container path means `/root`. |

```toml
agent = "opencode"
image = "paddock-opencode:latest"

[agents.opencode.server]
image = "paddock-opencode:latest"

[agents.opencode.server.build]
dockerfile = "~/src/paddock/images/Dockerfile"
policy = "weekly"

[agents.opencode.server.volumes]
"~/code" = "/home/alice/code:rw"
```

**One source.** Every project shares the server, so no project may configure it:

- In a `[projects]` entry, `server` is an error, in every project, until you remove it:
  `[user:projects.<path>.agents.<name>.server] Unexpected key "server".`
- In a project file, paddock discards it with a
  [warning](project-config.md#warning-behaviour), whatever the allowlist grants, and
  the rest of the file still applies.

**Paths** (`build.context`, `build.dockerfile` and the host side of `volumes`) must be
absolute or start with `~`, since a path relative to the workdir would differ by
project. They must exist, but paddock checks only the server the run chooses, so a
stale path under a server you aren't using stops nothing.

**Settings reach the server when paddock creates its container**, which it does on the
first run that finds none, or finds it stopped. A running server is used as it is: when
its image, port or mounts differ from your config, the run warns and names the command
that removes it, `docker rm -f paddock-server-<name>`, after which the next run creates
it afresh. Removing a server ends every project's sessions in progress. `build` applies
at the same moment, so a `policy` of `daily` or `weekly` rebuilds only when the server
is next created, not while it runs.

The server's `build` and the top-level one are independent, and paddock starts the
server before it builds the client's image. To build one image for both from a
Dockerfile, put the Dockerfile under the server's `build` and give the top-level
[`image`](#image) the same tag with no top-level `build.dockerfile`: the client then
runs the image the server's build produced.

A mount in `volumes` at exactly the container path of one of the server's own mounts
replaces it; that is how you
[share OpenCode's data with the host](agents/opencode.md#sharing-opencodes-data-with-the-host).

A run that chooses a server needs Docker Engine 25.0 or newer. Settings for a name no
installed server has are ignored with a [warning](#agent-servers).

### `build.args`

Build arguments (`docker build --build-arg`) for when paddock builds the image.

- **Type:** table of strings, argument name to value
- **Default:** none
- **TOML:** `NODE_VERSION = "24"` under `[build.args]`
- **Environment:** none. `PADDOCK_BUILD_ARGS`, or a name such as
  `PADDOCK_BUILD_ARGS_NODE_VERSION`, stops paddock with an
  [`Unexpected key` error](#troubleshooting).
- **Command line:** `--build-args-NODE_VERSION=24`, repeatable. The `=` is required,
  and `-` in the name becomes `_`.
- **Allowlist path:** `build.args` (or `build`)

Has no effect without [`build.dockerfile`](#builddockerfile). Use it to set the `ARG`s
your Dockerfile declares; the bundled Dockerfile's `ARG`s are listed under
[Docker Image](https://phx-paddock.readthedocs.io/en/latest/#docker-image).

paddock also passes the agent's `AGENT` argument, which a `build.args.AGENT` overrides,
and which a Dockerfile without `ARG AGENT` ignores.

```toml
[build.args]
NODE_VERSION = "24"
PYTHON_VERSION = "3.14"
```

### `build.context`

The directory sent to Docker as the build context, when paddock builds the image.

- **Type:** path to an existing directory
- **Default:** the directory containing [`build.dockerfile`](#builddockerfile)
- **TOML:** `context = "~/src/images"` under `[build]`
- **Environment:** `PADDOCK_BUILD_CONTEXT=~/src/images`
- **Command line:** `--build-context=~/src/images`
- **Allowlist path:** `build.context` (or `build`)

Has no effect without `build.dockerfile`. Set it when the Dockerfile `COPY`s files from
outside its own directory; the bundled Dockerfile `COPY`s nothing, so it needs none.
Relative paths resolve against the workdir; see [Validation](#validation).

### `build.dockerfile`

A Dockerfile paddock builds into [`image`](#image) before running it. Setting it turns
on building; without it, [`build.policy`](#buildpolicy) pulls the image instead.

- **Type:** path to an existing file
- **Default:** none — paddock runs `image` as is, and Docker pulls it if missing
- **TOML:** `dockerfile = "~/src/images/Dockerfile"` under `[build]`
- **Environment:** `PADDOCK_BUILD_DOCKERFILE=~/src/images/Dockerfile`
- **Command line:** `--build-dockerfile=~/src/images/Dockerfile`
- **Allowlist path:** `build.dockerfile` (or `build`)

Use it to keep an image in step with a Dockerfile rather than building it by hand.
Before each run, [`build.policy`](#buildpolicy) decides whether paddock runs:

```
docker build -t <image> -f <build.dockerfile> [--build-arg …] <build.context>
```

`--dry-run` never builds.

> [!WARNING]
> **The build applies to whichever `image` the run ends up with**
>
> With `build.dockerfile` in your user file, a per-project `image` or an
> `--image=ubuntu:26.04` gets built from your Dockerfile too, replacing the image of
> that name. No source can switch building off once a lower one turns it on, so set
> `[build]` beside the one `image` it builds: in a [`projects`](#projects) entry, or in
> your user file only if you never run another image. To run a prebuilt image in one
> project under a user-level build, set `policy = "if-missing"` under that project's
> `[projects."<workdir>".build]` and `docker pull` the image before its first run:
> paddock never rebuilds an image that exists locally under that policy.

[`build.args`](#buildargs) and [`build.context`](#buildcontext) have no effect without
this one.

To start from the bundled Dockerfile, copy it from
[`images/`](https://github.com/todofixthis/paddock/tree/main/images). For what any
image needs to work with paddock, see [Custom Docker Images](docker-images.md).

```toml
[projects."/home/alice/code/widgets"]
image = "widgets-dev:latest"

[projects."/home/alice/code/widgets".build]
dockerfile = "~/src/paddock/images/Dockerfile"
policy = "weekly"
```

Relative paths resolve against the workdir; see [Validation](#validation).

### `build.policy`

When paddock builds the image, or pulls it if no
[`build.dockerfile`](#builddockerfile) is set.

- **Type:** `"always"`, `"daily"`, `"if-missing"` or `"weekly"`
- **Default:** `"if-missing"`
- **TOML:** `policy = "daily"` under `[build]`
- **Environment:** `PADDOCK_BUILD_POLICY=daily`
- **Command line:** `--build-policy=daily`
- **Allowlist path:** `build.policy` (or `build`)

| Value | paddock builds or pulls when |
|---|---|
| `always` | Every run. |
| `daily` | The image is missing, or paddock last built or pulled it more than 24 hours ago. |
| `if-missing` | No image by that name exists locally. |
| `weekly` | The image is missing, or paddock last built or pulled it more than 7 days ago. |

After editing the Dockerfile, run `--build-policy=always` once from a project that
builds it, rather than changing the policy in a file.

paddock stamps each build with a `paddock.built-at` label and measures age from it, or
from the image's creation time for an image paddock didn't build. It builds with
Docker's layer cache, which replays an unchanged `RUN` step, so a `daily` or `weekly`
rebuild reinstalls nothing that step doesn't pin; see
[stale installs](docker-images.md#stale-installs) for the fixes.

Without `build.dockerfile`, paddock runs `docker pull <image>` when the policy says it's
due, so a registry image built on a schedule stays current. It records each pull in
`$XDG_STATE_HOME/paddock/pulls.json` (`~/.local/state/paddock/pulls.json` by default),
and under `always`, `daily` and `weekly` counts an image it has no record of pulling as
due. A due pull that fails, offline say, stops the run with Docker's error, and every
run stops until a pull succeeds; pass `--build-policy=if-missing` to run the local copy
meanwhile. A `build.dockerfile` from any source wins over pulling, so under a user-level
one no project can pull; see [`build.dockerfile`](#builddockerfile).

paddock records pulls per image reference, as written, not per project, so projects
naming the same image share its record. With this user file, paddock pulls `:python` at
most once a day however many projects run it, and `:infra`, which only the infra project
runs, likewise:

```toml
image = "ghcr.io/your-name/agent:python"

[build]
policy = "daily"

[projects."/home/alice/code/infra"]
image = "ghcr.io/your-name/agent:infra"

[projects."/home/alice/code/widgets"]
image = "widgets-dev:latest"

[projects."/home/alice/code/widgets".build]
policy = "if-missing"
```

The widgets project runs an image built by hand and never pushed, so it opts out of the
daily pull and pulls only if the image goes missing; without that, the caution below
applies to it.

> [!CAUTION]
> **A periodic policy in your user file or environment pulls every project's image**
>
> Every project whose `image` has no Dockerfile gets pulled, including a tag you only
> ever built locally. With no record of pulling it, paddock tries at once, and a failed
> pull records nothing, so every run stops; where a registry you don't control has an
> image of that name, the pull instead replaces yours with it. Fully qualify the
> images you pull (`ghcr.io/your-name/your-image:latest`), and opt a project out of a
> user-file policy with `policy = "if-missing"` under its `[projects."<workdir>".build]`.
> A `.paddock/config.toml` can't opt out, and nothing but `--build-policy` overrides an
> exported `PADDOCK_BUILD_POLICY`.

### `config.allowlist`

Which keys each gated source may set. This is how you enable
[project-level config](project-config.md).

- **Type:** table with keys `cli`, `env` and `project_toml`; each is `true`, `false`, or
  a list of allowlist paths
- **Default:** `cli = true`, `env = true`, `project_toml = false`
- **TOML:** `project_toml = ["volumes"]` under `[config.allowlist]` in the user file, or
  under `[projects."<workdir>".config.allowlist]` for one project
- **Environment:** none
- **Command line:** none
- **Allowlist path:** none — it can't be gated

| Value | Effect |
|---|---|
| `true` | The source may set any directive. |
| `false` or `[]` | The source is blocked. |
| A list, e.g. `["image", "build.dockerfile"]` | The source may set only the directives listed. |

List entries are the allowlist paths named under each directive: `agent`, `agents`,
`build`,
`build.args`, `build.context`, `build.dockerfile`, `build.policy`, `image`, `network`
and `volumes`. `build` covers all of `build.*`. `agent` and
`agents` are different grants: the first lets a source choose the agent and its
server, the second set any agent's arguments. No grant lets a source set
[`agents.<name>.server`](#agentsnameserver). paddock rejects any other entry when it
loads the user file.

paddock drops a blocked key with a warning rather than an error. The user file and
`[projects]` overrides are yours, so they can't be gated.

A rule under `[projects."<workdir>".config.allowlist]` replaces your user-level rule for
that source, rather than adding to it:

```toml
[config.allowlist]
project_toml = ["volumes"]

# This project may also choose its image, and still its volumes
[projects."/home/alice/code/widgets".config.allowlist]
project_toml = ["image", "volumes"]
```

Before granting `project_toml`, read
[what each key hands a committed file](project-config.md#enabling-project-level-config).
For the full behaviour, see [The allowlist](project-config.md#the-allowlist).

### `config.project_dir_readonly`

Whether the container may write to the project's `.paddock/` directory.

- **Type:** boolean
- **Default:** `true` (read-only)
- **TOML:** `project_dir_readonly = false` under `[config]` in the user file, or under
  `[projects."<workdir>".config]` for one project
- **Environment:** none
- **Command line:** none
- **Allowlist path:** none — it can't be gated

Matters only once `project_toml` is enabled: paddock then mounts `<workdir>/.paddock/`
at the same path in the container. Set `false` to let the agent keep state there between
runs. A `[projects."<workdir>"]` value beats the user-level one. See
[The `.paddock` directory](project-config.md#the-paddock-directory).

The setting covers the agent's own container. An agent with a server runs its tools in
the server, which reaches `.paddock/` through its own mounts whatever this says; see
the [`opencode` agent](agents/opencode.md#what-the-agent-can-reach).

### `image`

The Docker image to run. Required.

- **Type:** non-empty string, any reference `docker run` accepts
- **Default:** none — the run stops with `[final:image] Non-empty value expected.`
- **TOML:** `image = "paddock-claude:latest"`
- **Environment:** `PADDOCK_IMAGE=paddock-claude:latest`
- **Command line:** `--image=paddock-claude:latest`
- **Allowlist path:** `image`

With [`build.dockerfile`](#builddockerfile) set, this is also the tag paddock builds.
Without it, Docker pulls the image on first use if it isn't local, and
[`build.policy`](#buildpolicy) can keep it current.

The image must have the agent's command on its `PATH` and run as root; see
[Custom Docker Images](docker-images.md). Set `image` in your user file, and per project
where a project needs a different toolchain — but see
[`build.dockerfile`](#builddockerfile) before combining a per-project image with a
user-level build.

An agent's server runs an image of its own,
[`agents.<name>.server.image`](#agentsnameserver), which can be set only in the global
section of your user file, never per project. Where the server runs the agent's tools,
as `opencode`'s does, a per-project `image` changes the interface's container alone:
every project shares the server's toolchain.

### `network`

A Docker network to attach the container to.

- **Type:** string
- **Default:** none — Docker's default bridge network
- **TOML:** `network = "dev-services"`
- **Environment:** `PADDOCK_NETWORK=dev-services`
- **Command line:** `--network=dev-services`
- **Allowlist path:** `network`

Use it when the agent needs to reach other containers by name, such as a database
started by Docker Compose (whose network is usually `<project>_default`). The network
must already exist; `docker network ls` lists them, including Docker's built-in `bridge`,
`host` and `none`. paddock logs the other containers on it before starting. `host`
shares the host's network stack, removing network isolation; `none` cuts the container
off from any network, the agent's API included.

An empty value removes a network set by a lower-weight source, leaving Docker's default
bridge: `network = ""` in `[projects."<workdir>"]`, or `--network=`. An empty
`PADDOCK_NETWORK` is ignored.

A client paired with a [server](#agentsnameserver), as `opencode` is, joins the
server's network, `paddock-server-<name>`, as well as this one. Docker can't combine a
second network with `bridge`, `default`, `host`, `none` or `container:<name>`, so each
of those stops a paired run:

```
[network] "host" cannot be combined with a server's network; agent "opencode" is paired with server "opencode"
```

Any network you created yourself works.

### `projects`

Settings for one project, kept in your user file rather than in the project.

- **Type:** table keyed by absolute workdir path; each entry takes any directive here
  except `projects`
- **Default:** none
- **TOML:** user file only: `[projects."/home/alice/code/widgets"]`
- **Environment:** none
- **Command line:** none
- **Allowlist path:** none — it can't be gated

paddock uses the entry whose key equals the workdir, resolved to an absolute path with
symlinks followed. `~` in the key isn't expanded, and an entry for a parent directory
doesn't apply to its subdirectories. Entries outweigh the rest of your user file but
not the environment or command line. paddock checks every entry's keys and values on
each run, but an entry's paths only when it applies. A key that can never match, such
as `~/code/widgets`, a relative path or one with a trailing slash, stops every run. An
entry keyed by a symlink, or for a project you have since moved, is ignored without a
warning; re-key it to the project's real, current path.

Use it for per-project settings you don't want to commit, or a per-project
[`config.allowlist`](#configallowlist):

```toml
image = "paddock-claude:latest"

[projects."/home/alice/code/widgets"]
image = "widgets-dev:latest"
network = "widgets_default"

[projects."/home/alice/code/widgets".volumes]
"~/datasets/widgets" = "/data:ro"
```

### `volumes`

Extra host directories or files to mount into the container.

- **Type:** table, host path to container path with an optional `:ro` or `:rw` mode
- **Default:** none. paddock always mounts the workdir read-write at the same path,
  plus the agent's mounts.
- **TOML:** `"~/datasets" = "/data:ro"` under `[volumes]`
- **Environment:** none. `PADDOCK_VOLUMES`, or a name such as `PADDOCK_VOLUMES_DATA`,
  stops paddock with an [`Unexpected key` error](#troubleshooting).
- **Command line:** `--volume=~/datasets:/data:ro`, repeatable
- **Allowlist path:** `volumes`

Use it to give the agent things outside the workdir: reference data, a sibling
repository, a credentials file. These mount into the run's own container. An agent
whose tools run in a server, as `opencode`'s do, reaches only what the server mounts:
list them under [`agents.<name>.server`](#agentsnameserver) instead.

- **Host path** (the key): must exist when paddock starts. Expands a leading `~` to
  your home directory; relative paths resolve against the workdir (see
  [Validation](#validation)).
- **Container path:** must be absolute. A leading `~` expands to `/root`.
- **Mode:** `ro` (read-only, the default) or `rw`, in either case. Mount read-write only
  what the agent should be able to change on your machine.

On the command line, the first `:` separates host from container path, so a host path
containing `:` needs a TOML file. Sources merge volumes per host path; see
[Precedence](#precedence).

```toml
[volumes]
"~/datasets" = "/data"
"~/code/widgets-api" = "/root/widgets-api:rw"
"/etc/ssl/certs/corp-ca.pem" = "/usr/local/share/ca-certificates/corp-ca.crt"
```

A project can declare its own mounts in `.paddock/config.toml`, once each developer
grants it the `volumes` key.

> [!CAUTION]
> **Granting `volumes` lets a project mount any file or directory**
>
> A project file allowed `volumes` can mount any path on your machine, in either mode —
> including your home directory, `~/.ssh`, etc. Grant it only to projects you trust, and
> only under that project's `[projects."<workdir>".config.allowlist]`. Better still, put
> the mounts in your own `[projects."<workdir>".volumes]` and grant the project file
> nothing.

```toml
# <workdir>/.paddock/config.toml, committed with the project
[volumes]
"~/datasets/widgets" = "/data:ro"
```

```toml
# ~/.config/paddock/config.toml, on each developer's machine
[projects."/home/alice/code/widgets".config.allowlist]
project_toml = ["volumes"]
```

Relative paths in a committed file resolve against the project, so they suit a shared
file best: `"../widgets-api"` works for every developer who clones the two side by side.
`~` expands against each developer's own home directory. Every developer who enables
the project file needs every host path, even one whose grant leaves out `volumes`, or
paddock stops before starting (see [Validation](#validation)). A mount that varies per
developer, such as a sibling repository cloned somewhere different on each machine,
belongs in each developer's own [`projects`](#projects) entry instead.

## Troubleshooting

Messages that point at the project file or the allowlist are covered under
[Troubleshooting](project-config.md#troubleshooting) on the project-config page.

**`[user:<key>] …`**

Your user file has invalid TOML or a bad value; `<key>` names the field. Common causes:
a misspelt key (`imgae`), `[agent.<name>]` written for
[`[agents.<name>]`](#agentsnameextra_args) (reported at `agent.<name>`; when the file
also sets `agent` to a name, as `[user] This value is not valid TOML.`, repeated for
`[project_overrides]`), an `[agent]` header in a file that also sets `agent` to a name
(the same `not valid TOML` message; write `agent = { client = "…", server = "…" }`
instead), an allowlist source other than `cli`, `env` and
`project_toml`, or an allowlist value that isn't `true`, `false` or a list of
[allowlist paths](#configallowlist).

**`[agents.<name>] No agent named "<name>" is installed, so its settings are ignored; installed agents: …`**

A warning, not an error: the run goes ahead without those settings. Either `<name>` is
misspelt under [`agents`](#agentsnameextra_args), in your user file or a granted
project file, or it names an agent from a package this machine lacks. Only `--quiet`
hides it, along with every other warning and the printed command.

**`[env:PADDOCK_…] Unexpected key "PADDOCK_…".`**

A `PADDOCK_*` variable that matches no directive, even with an empty value. Usually
it's a typo: unset or correct it. If the directive has no environment variable (🚫 in
the [reference table](#reference-table)), no spelling works: unset the variable and set
the directive in a TOML file, or for [`build.args`](#buildargs) and
[`volumes`](#volumes) with `--build-args-KEY=VALUE` or `--volume`.

**`[<source>:volumes.<host path>] Path '…' does not exist or cannot be resolved (checked …).`**

A volume's host path doesn't exist. A relative one is checked against the workdir, not
where you ran paddock; see [Validation](#validation). The path after `checked` is the
one paddock looked for.

**`[user:projects.<path>…] …` or `[project_overrides:…] …`**

A `[projects]` entry has a misspelt key, a bad value, a key that can never match a
workdir or, for `project_overrides`, a path that doesn't exist. `project_overrides` is
the entry for this workdir; a `user:projects` error may come from any entry, since
paddock checks every entry's keys and values on each run. A typo in this workdir's
entry appears under both names. See [`projects`](#projects) and
[Validation](#validation).

**`[<source>:build.…] Expected a file, but '…' is a directory (…).`**

`build.dockerfile` names a directory, or `build.context` a file (`Expected a directory,
but '…' is not a directory`). The path in brackets is the one paddock checked.

**`[agent] Unknown agent "…"; installed agents: …`**

Use one of the agents listed, or install the package that provides yours.
`[agent.server] Unknown server "…"; installed servers: …` is the same for the server
half of [`agent`](#agent).

**`[final:image] Non-empty value expected.`**

No source sets [`image`](#image). Set it in your user file or pass `--image`.

**A Docker error right after `Pulling …`**

[`build.policy`](#buildpolicy) is pulling the image, and the pull failed. Offline, pass
`--build-policy=if-missing` to run your local copy until you're back. For an image that
should come from a registry, check [`image`](#image) for a typo and, for a private one,
run `docker login` (GitHub packages are private by default). For one you only built
locally, set `policy = "if-missing"` under that project's `[projects."<workdir>".build]`:
paddock never pulls an image that exists locally under that policy.

**`[workdir] Path "…" does not exist or is not a directory`**

`--workdir`, or the current directory, isn't a directory. paddock stops before reading
any config.

**`Reading user config from … because XDG_CONFIG_HOME is set and … does not exist. This fallback is deprecated …`**

Your user file is still at `~/.config/paddock/config.toml`, but `XDG_CONFIG_HOME`
points elsewhere. Move it to the path the warning gives; paddock 2.0 stops reading the
old one. Set `XDG_CONFIG_HOME` everywhere you run paddock (IDE, cron, `sudo`): a run
without it reads only `~/.config/paddock/`.

**`Ignoring … because XDG_CONFIG_HOME is set; reading user config from ….`**

You have a user file in both places, and paddock reads only the XDG one. Merge what the
old file still needs into the XDG one, then delete the old file.

### Agent servers

Messages from a run that chooses an [agent server](#agentsnameserver), in the order a
run can meet them. Each stops the run with exit status 1 unless marked a warning.
`<name>` is the server's name, e.g. `opencode`.

**`[user:projects.<path>.agents.<name>.server] Unexpected key "server".`**

Server settings sit in a `[projects]` entry. Every project shares the server, so move
them to `[agents.<name>.server]` in the global section of your user file. Until you do,
this stops runs in every project, not only `<path>`.

**`project_toml: ignored agents.<name>.server — server settings are read only from the global section of your user config`**

A warning. The project file tried to configure the shared server, and paddock discarded
that table and applied the rest. If the file is not yours, treat it as a reason to look
at what else it sets.

**`[agents.<name>.server] No server named "<name>" is installed, so its settings are ignored; installed servers: …`**

A warning. `<name>` is misspelt under `[agents.<name>.server]`, or names a server from a
package this machine lacks.

**`[user:agents.<name>.server.…] Path '…' must be absolute: a shared server's paths cannot depend on the workdir.`**

A server's `build.context`, `build.dockerfile` or volume host path is relative. Write it
in full, or from `~`.

**`[agents.<name>.server.image] No image is set, and server "<name>" has no default`**

Set `image` under `[agents.<name>.server]`. The top-level [`image`](#image) is the
client's and does not stand in for it.

**`[agents.<name>.server.volumes.<host path>] Path '…' does not exist or cannot be resolved (checked …).`**

A host path the server mounts doesn't exist; create it or remove the entry. The same
message at `agents.<name>.server.build.context` or `….build.dockerfile` names a missing
build path, and `Expected a file, but '…' is a directory (…)` or `Expected a directory,
but '…' is not a directory (…)` one of the wrong kind.

**`[agent] Agent "…" needs a server that speaks "…", but none is chosen; set agent.server`**

The client can't run without its server, and the server half of [`agent`](#agent) is
`false`: look for `server = false`, `PADDOCK_AGENT_SERVER=false` or
`--agent-server=false`. Remove it, or name the server. The variant ending
`but server "…" speaks "…"` means the server chosen is another agent's.

**`[network] "…" cannot be combined with a server's network; agent "…" is paired with server "…"`**

[`network`](#network) is `bridge`, `default`, `host`, `none` or `container:…`, none of
which Docker can combine with the server's network. Name a network you created, or
unset it: `--network=` for one run.

**`[docker] Agent servers need Docker Engine 25.0 or newer (API 1.44); found API …`**

Upgrade Docker. The API version found is the older of the client's and the daemon's.

**`[docker] Could not read the Docker version: …`**

`docker version` failed, usually because no daemon is running; the text after the colon
is Docker's own reason.

**`[agent.server] A container named "paddock-server-<name>" exists that paddock did not create; remove or rename it`**

Something else owns the name paddock gives the server. paddock won't touch a container
it didn't create. `[docker] A network named "paddock-server-<name>" exists that paddock
did not create; remove or rename it` is the same for the network.

**`[agent.server] Server "<name>" does not have <workdir> mounted read-write at the same path; its mounts: …`**

The server runs the agent's tools, so the workdir must be under one of its read-write
mounts, at the same path as on the host. Add the mount under
`[agents.<name>.server.volumes]`; if the message ends with a `docker rm -f` command, a
server is running without it, and that command removes it so the next run can create
one that has it. See
[What the agent can reach](agents/opencode.md#what-the-agent-can-reach).

**`[agent.server] Could not build or pull the image for server "<name>": docker exited …`**

The server's `build` settings ran `docker build` or `docker pull`, and it failed.
Docker's own output, above the message, says why.

**`[docker] Could not start "paddock-server-<name>": …`**

Docker refused to create the server's network or container; the text after the colon is
Docker's reason. Common causes: the image doesn't exist locally and can't be pulled,
or the [`port`](#agentsnameserver) you set is already in use.

**`[agent.server] Server "<name>" stopped while starting; see: docker logs paddock-server-<name>`**

The server's command exited. Read the logs before running paddock again: the next run
removes the stopped container, and its logs with it.

**`[agent.server] Server "<name>" was not ready after 30 seconds; see: docker logs paddock-server-<name>`**

The container is running but the server isn't answering. The logs say what it is
doing. A server that is only slow to start is left running, so running paddock again
may find it ready.

**`[agent.server] Server "<name>" was created but never started; it has been removed, so run again`**

paddock found the container created but not started, waited 30 seconds, and removed it.
Run again to create a new one.

**`[agent.server] Server "<name>" is running without a secret paddock can read; to recreate it: docker rm -f paddock-server-<name>`**

The running container lacks the secret paddock gives each server, so no client can
connect. Run the command; it ends every project's sessions in progress.

**`Server "<name>" is running with settings that differ from your config; they apply when it is recreated: docker rm -f paddock-server-<name>`**

A warning: the run goes ahead against the server as it is. Its image, port or mounts
differ from your config. Run the command when you are ready to end every project's
sessions in progress; the next run creates the server from your settings.
