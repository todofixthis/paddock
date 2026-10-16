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
[`volumes`](#volumes) and [`build.args`](#buildargs) still add to yours (see below).
[Precedence](project-config.md#precedence) on the project-config page walks through an
example.

Merging is per key, not per source:

- **Single values** (`image`, `network`, `build.policy` …): the highest-weight source
  that sets one wins.
- **`[build]`**: each key merges separately, and `build.args` merges per argument
  name. A per-project `build.policy` keeps your user-level `build.dockerfile`.
- **`[volumes]`**: merge per host path. Sources add mounts; a higher-weight source can
  change the container path or mode of a host path a lower one mounts, but not remove
  it.

Higher sources cannot unset a value, with one exception: an empty
[`network`](#network) falls back to Docker's default network.

### Validation

paddock validates every enabled source before merging, then the merged result. Any
error stops the run before Docker starts, naming the source and key:

```
[user:build.dockerfile] Path 'images/Dockerfile' does not exist or cannot be resolved.
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
of the project. A `[projects."<path>"]` entry resolves against its `<path>`, the workdir
it applies to. The workdir here is its real path, with symlinks resolved, so `..`
climbs from a symlinked checkout's target, not the link.

A relative path you set once for every project, in the global section of your user
file, an exported `PADDOCK_*` variable or a shell alias, therefore names a different
directory in each project, and stops any run in a project that lacks it. Use an
absolute or `~` path for anything that lives in one place, such as a Dockerfile beside
your user file, and put a mount only some projects have in their
[`projects`](#projects) entries.

> [!WARNING]
> **A stale `[projects]` entry stops every run**
>
> paddock validates every `[projects]` entry on each run, not just the current one. An
> entry with a path that no longer exists stops every run, whichever project you are
> in. That is usually a relative path whose base has gone: the entry's project was
> moved or deleted, or its key isn't a real directory, such as a typo or a `~` key. The
> error names that entry:
>
> ```
> [user:projects./home/alice/code/gone.volumes.data] Path 'data' does not exist or cannot be resolved.
> ```
>
> Remove or fix the stale entry.

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
| Agent arguments | `paddock -- --continue` | Everything after `--` is appended to the agent's command: `claude --continue`. |
| Command | `paddock /bin/bash` | The first positional argument, and everything after it, replaces the agent's command. Put paddock flags first. |
| Dry run | `--dry-run` | Prints the `docker run` command and exits 0 without building or running anything. |
| Help | `--help` | Prints usage and exits. |
| Quiet | `--quiet` | Suppresses logging, warnings and the printed `docker run` command. Errors still print. |
| Version | `--version` | Prints the paddock version and exits. |
| Workdir | `--workdir=PATH` | Mounts `PATH` as the workspace instead of the current directory. paddock resolves it to an absolute real path first, and that path is the key [`projects`](#projects) matches. |

A prompt needs `--` in front of it: `paddock "fix this bug"` tries to execute a command
named `fix this bug`. Flags before `--` must be spelt in full; paddock rejects
abbreviations and unknown flags. paddock exits with the container's exit status, 1 on a
config error and 2 on an unknown flag.

## Directives

### `agent`

The coding agent to run in the container, or `false` for a plain bash shell.

- **Type:** agent name (string), or `false`
- **Default:** `"claude"`
- **TOML:** `agent = "claude"`, or `agent = false` (the string `"false"` also works)
- **Environment:** `PADDOCK_AGENT=claude`
- **Command line:** `--agent=claude`
- **Allowlist path:** `agent`

The agent decides:

- **The command.** `claude` runs `claude`; `false` runs `/bin/bash`.
- **Extra mounts.** `claude` mounts your `~/.claude` read-write at `/root/.claude`, plus
  `~/.claude.json` if it exists, so sign-in and settings persist between runs. `false`
  mounts nothing extra.
- **The `AGENT` build argument** passed when paddock [builds the image](#builddockerfile):
  `claude` for `claude`, `none` for `false`.
- **The container name**, `paddock-<workdir name>-<agent>`.

Installed packages can add agents; see
[Adding agents](https://phx-paddock.readthedocs.io/en/latest/#adding-agents). An unknown
name stops the run and lists the installed agents:

```
[agent] Unknown agent "claud"; installed agents: claude, false
```

Use `false` to explore an image or debug it. With [`build.dockerfile`](#builddockerfile)
set, though, a rebuild under `false` tags the same [`image`](#image) with `AGENT=none`,
replacing an image that had the agent installed. To get a shell in your agent's image,
pass a [command](#run-options) instead: `paddock /bin/bash`.

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
on building.

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
> `--image=ubuntu:24.04` gets built from your Dockerfile too, replacing the image of
> that name. No source can switch building off once a lower one turns it on, so set
> `[build]` beside the one `image` it builds: in a [`projects`](#projects) entry, or in
> your user file only if you never run another image. To run a prebuilt image in one
> project under a user-level build, set `policy = "if-missing"` under that project's
> `[projects."<workdir>".build]` and `docker pull` the image before its first run:
> paddock never rebuilds an image that exists locally under that policy.

Every other `build` directive needs this one: setting `build.policy` alone stops the run
with `[final:build.dockerfile] Non-empty value expected.`

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

When paddock rebuilds the image.

- **Type:** `"always"`, `"daily"`, `"if-missing"` or `"weekly"`
- **Default:** `"if-missing"`
- **TOML:** `policy = "daily"` under `[build]`
- **Environment:** `PADDOCK_BUILD_POLICY=daily`
- **Command line:** `--build-policy=daily`
- **Allowlist path:** `build.policy` (or `build`)

| Value | paddock builds when |
|---|---|
| `always` | Every run. |
| `daily` | The image is missing, or paddock last built it more than 24 hours ago. |
| `if-missing` | No image by that name exists locally. |
| `weekly` | The image is missing, or paddock last built it more than 7 days ago. |

After editing the Dockerfile, run `--build-policy=always` once from a project that
builds it, rather than changing the policy in a file. Has no effect without [`build.dockerfile`](#builddockerfile).

paddock stamps each build with a `paddock.built-at` label and measures age from it, or
from the image's creation time for an image paddock didn't build.

> [!WARNING]
> **`daily` and `weekly` don't update unpinned installs**
>
> paddock builds with Docker's layer cache, which replays an unchanged `RUN` step, so a
> rebuild reinstalls nothing that step doesn't pin, the bundled Dockerfile's agent
> included. See [stale installs](docker-images.md#stale-installs) for the fixes.

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

List entries are the allowlist paths named under each directive: `agent`, `build`,
`build.args`, `build.context`, `build.dockerfile`, `build.policy`, `image`, `network`
and `volumes`. `build` covers all of `build.*`. paddock rejects any other entry when it
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

### `image`

The Docker image to run. Required.

- **Type:** non-empty string, any reference `docker run` accepts
- **Default:** none — the run stops with `[final:image] Non-empty value expected.`
- **TOML:** `image = "paddock-claude:latest"`
- **Environment:** `PADDOCK_IMAGE=paddock-claude:latest`
- **Command line:** `--image=paddock-claude:latest`
- **Allowlist path:** `image`

With [`build.dockerfile`](#builddockerfile) set, this is also the tag paddock builds.
Without it, Docker pulls the image on first use if it isn't local.

The image must have the agent's command on its `PATH` and run as root; see
[Custom Docker Images](docker-images.md). Set it in your user file, and per project
where a project needs a different toolchain — but see
[`build.dockerfile`](#builddockerfile) before combining a per-project image with a
user-level build.

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
not the environment or command line.

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
repository, a credentials file.

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
a misspelt key (`imgae`), an allowlist source other than `cli`, `env` and
`project_toml`, or an allowlist value that isn't `true`, `false` or a list of
[allowlist paths](#configallowlist).

**`[env:PADDOCK_…] Unexpected key "PADDOCK_…".`**

A `PADDOCK_*` variable that matches no directive, even with an empty value. Usually
it's a typo: unset or correct it. If the directive has no environment variable (🚫 in
the [reference table](#reference-table)), no spelling works: unset the variable and set
the directive in a TOML file, or for [`build.args`](#buildargs) and
[`volumes`](#volumes) with `--build-args-KEY=VALUE` or `--volume`.

**`[<source>:volumes.<host path>] Path '…' does not exist or cannot be resolved.`**

A volume's host path doesn't exist. A relative one is checked against the workdir, not
where you ran paddock; see [Validation](#validation).

**`[user:projects.<path>.…] Path '…' does not exist or cannot be resolved.`**

A `[projects]` entry, possibly for a project other than this one, names a path that
doesn't exist. paddock validates every entry on each run; see [Validation](#validation).

**`[agent] Unknown agent "…"; installed agents: …`**

Use one of the agents listed, or install the package that provides yours.

**`[final:image] Non-empty value expected.`**

No source sets [`image`](#image). Set it in your user file or pass `--image`.

**`[final:build.dockerfile] Non-empty value expected.`**

A source sets a `build` directive but none sets
[`build.dockerfile`](#builddockerfile).

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
