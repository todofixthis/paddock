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
follows symlinks.

> [!WARNING]
> **Relative paths resolve against your shell's directory**
>
> paddock resolves a relative path against the directory you run paddock from, not the
> workdir or the config file's directory, so `"data"` in `.paddock/config.toml` breaks
> when you pass `--workdir`. Use absolute or `~`-relative paths.

## Reference table

`—` marks a source that can't set the directive. Cells in the `[projects."<workdir>"]`
column go under that table header.

TOML cells use [dotted keys](https://toml.io/en/v1.0.0#keys): `build.policy = "daily"`
is `policy = "daily"` under `[build]`. A dotted key after a `[table]` header belongs to
that table, so put dotted keys above the first header. A file can't use both forms for
one table: `volumes."~/x" = "/x"` beside a `[volumes]` header fails to parse, so add to
the existing table instead.

| Directive | `config.toml` (user) | `[projects."<workdir>"]` | `.paddock/config.toml` | Environment | Command line |
|---|---|---|---|---|---|
| [`agent`](#agent) | `agent = "claude"` | `agent = "claude"` | `agent = "claude"` | `PADDOCK_AGENT=claude` | `--agent=claude` |
| [`build.args`](#buildargs) | `build.args.NODE_VERSION = "24"` | `build.args.NODE_VERSION = "24"` | `build.args.NODE_VERSION = "24"` | — | `--build-args-NODE_VERSION=24` |
| [`build.context`](#buildcontext) | `build.context = "~/src/images"` | `build.context = "~/src/images"` | `build.context = "~/src/images"` | `PADDOCK_BUILD_CONTEXT=~/src/images` | `--build-context=~/src/images` |
| [`build.dockerfile`](#builddockerfile) | `build.dockerfile = "~/src/images/Dockerfile"` | `build.dockerfile = "~/src/images/Dockerfile"` | `build.dockerfile = "~/src/images/Dockerfile"` | `PADDOCK_BUILD_DOCKERFILE=~/src/images/Dockerfile` | `--build-dockerfile=~/src/images/Dockerfile` |
| [`build.policy`](#buildpolicy) | `build.policy = "daily"` | `build.policy = "daily"` | `build.policy = "daily"` | `PADDOCK_BUILD_POLICY=daily` | `--build-policy=daily` |
| [`config.allowlist`](#configallowlist) | `config.allowlist.project_toml = ["volumes"]` | `config.allowlist.project_toml = ["volumes"]` | — | — | — |
| [`config.project_dir_readonly`](#configproject_dir_readonly) | `config.project_dir_readonly = false` | `config.project_dir_readonly = false` | — | — | — |
| [`image`](#image) | `image = "paddock-claude:latest"` | `image = "paddock-claude:latest"` | `image = "paddock-claude:latest"` | `PADDOCK_IMAGE=paddock-claude:latest` | `--image=paddock-claude:latest` |
| [`network`](#network) | `network = "dev-services"` | `network = "dev-services"` | `network = "dev-services"` | `PADDOCK_NETWORK=dev-services` | `--network=dev-services` |
| [`projects`](#projects) | `[projects."/home/alice/code/widgets"]` | — | — | — | — |
| [`volumes`](#volumes) | `volumes."~/datasets" = "/data:ro"` | `volumes."~/datasets" = "/data:ro"` | `volumes."~/datasets" = "/data:ro"` | — | `--volume=~/datasets:/data:ro` |

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
| User config location | `XDG_CONFIG_HOME=/path` (environment) | Moves the user file; see [Where configuration comes from](#where-configuration-comes-from). |
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
- **TOML:** `build.args.NODE_VERSION = "24"`, or a `[build.args]` table
- **Environment:** none. `PADDOCK_BUILD_ARGS` is ignored, and a name such as
  `PADDOCK_BUILD_ARGS_NODE_VERSION` produces a garbled build argument rather than an
  error, so don't use either.
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
- **TOML:** `build.context = "~/src/images"`
- **Environment:** `PADDOCK_BUILD_CONTEXT=~/src/images`
- **Command line:** `--build-context=~/src/images`
- **Allowlist path:** `build.context` (or `build`)

Has no effect without `build.dockerfile`. Set it when the Dockerfile `COPY`s files from
outside its own directory; the bundled Dockerfile `COPY`s nothing, so it needs none.
Relative paths resolve against the directory you run paddock from; see
[Validation](#validation).

### `build.dockerfile`

A Dockerfile paddock builds into [`image`](#image) before running it. Setting it turns
on building.

- **Type:** path to an existing file
- **Default:** none — paddock runs `image` as is, and Docker pulls it if missing
- **TOML:** `build.dockerfile = "~/src/images/Dockerfile"`
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
> project under a user-level build, give that project's entry
> `build.policy = "if-missing"` and `docker pull` the image before its first run:
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

Relative paths resolve against the directory you run paddock from; see
[Validation](#validation).

### `build.policy`

When paddock rebuilds the image.

- **Type:** `"always"`, `"daily"`, `"if-missing"` or `"weekly"`
- **Default:** `"if-missing"`
- **TOML:** `build.policy = "daily"`
- **Environment:** `PADDOCK_BUILD_POLICY=daily`
- **Command line:** `--build-policy=daily`
- **Allowlist path:** `build.policy` (or `build`)

| Value | paddock builds when |
|---|---|
| `always` | Every run. |
| `daily` | The image is missing, or was created more than 24 hours ago. |
| `if-missing` | No image by that name exists locally. |
| `weekly` | The image is missing, or was created more than 7 days ago. |

After editing the Dockerfile, run `--build-policy=always` once from a project that
builds it, rather than changing the policy in a file. Has no effect without [`build.dockerfile`](#builddockerfile).

> [!NOTE]
> **`daily` and `weekly` don't update the agent**
>
> paddock builds with Docker's layer cache, and the layer that installs the agent is
> cached. A fully cached build also keeps the image's old creation time, so once the
> image passes the age limit, every run rebuilds from cache, quickly, until a layer
> changes. To refresh the agent, rebuild by hand with `docker build --no-cache`.

### `config.allowlist`

Which keys each gated source may set. This is how you enable
[project-level config](project-config.md).

- **Type:** table with keys `cli`, `env` and `project_toml`; each is `true`, `false`, or
  a list of allowlist paths
- **Default:** `cli = true`, `env = true`, `project_toml = false`
- **TOML:** user file or `[projects."<workdir>"]` only:
  `config.allowlist.project_toml = ["volumes"]`
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
- **TOML:** user file or `[projects."<workdir>"]` only:
  `config.project_dir_readonly = false`
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
- **TOML:** `volumes."~/datasets" = "/data:ro"`, or a `[volumes]` table
- **Environment:** none — set it in a TOML file or on the command line
- **Command line:** `--volume=~/datasets:/data:ro`, repeatable
- **Allowlist path:** `volumes`

Use it to give the agent things outside the workdir: reference data, a sibling
repository, a credentials file.

- **Host path** (the key): must exist when paddock starts. Expands a leading `~` to
  your home directory; relative paths resolve against the directory you run paddock
  from (see [Validation](#validation)).
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
> **Grant `volumes` for that project only**
>
> A global grant lets any repository you run paddock in mount any path in your home,
> `~/.ssh` included, read-write.

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

`~` in a committed file expands against each developer's own home directory, so
`~`-relative paths suit a shared file best; there is no way to name a path relative to
the project. Every developer who enables the project file needs every host path, even
one whose grant leaves out `volumes`, or paddock stops before starting (see
[Validation](#validation)). A mount that varies per developer, such as a sibling
repository cloned somewhere different on each machine, belongs in each developer's own
[`projects`](#projects) entry instead.

## Troubleshooting

Messages that point at the project file or the allowlist are covered under
[Troubleshooting](project-config.md#troubleshooting) on the project-config page.

**`[user:<key>] …`**

Your user file has invalid TOML or a bad value; `<key>` names the field. Common causes:
a misspelt key (`imgae`), an allowlist source other than `cli`, `env` and
`project_toml`, or an allowlist value that isn't `true`, `false` or a list of
[allowlist paths](#configallowlist).

**`[env:foo] Unexpected key "foo".`**

A `PADDOCK_*` variable that matches no directive, usually a typo. Unset or correct it.

**`[env:volumes] str is not valid (allowed types: dict).`**

[`volumes`](#volumes) has no environment variable. Use a TOML file or `--volume`.

**`[<source>:volumes.<host path>] Path '…' does not exist or cannot be resolved.`**

A volume's host path doesn't exist, or is relative and doesn't exist from where you ran
paddock. See [Validation](#validation).

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
