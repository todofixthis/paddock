# Project-Level Config and the Allowlist

## Overview

paddock reads two config files, among [other sources](configuration.md#where-configuration-comes-from):

- **User-level** (`$XDG_CONFIG_HOME/paddock/config.toml`, by default `~/.config/paddock/config.toml`) — your personal defaults, applied to every project.
- **Project-level** (`.paddock/config.toml` in the project workdir) — settings committed alongside a project and shared with everyone who works on it. It takes the same [directives](configuration.md#directives), except `config`, `projects` and an agent server's settings (`agents.<name>.server`), which paddock [ignores there](#warning-behaviour).

Because project-level config lives inside a project repository, paddock treats it as **untrusted by default**. A malicious or misconfigured project could otherwise redirect your Docker image, override your network settings, mount sensitive paths, or pass arguments to your agent. Even once enabled it carries the lowest [weight](#precedence) of any source, so it can't override a value you set — though it can add mounts and build arguments to yours, and arguments for an agent you have set none for. You must explicitly grant each project (or all projects) permission to contribute config before paddock will honour it.

User-level config is trusted: it's yours.

### What this protects against

The threat model is an **untrusted change landing in a repository** — a `.paddock/config.toml` committed by another contributor (or pulled in by an automated dependency update) that silently changes how your container runs. It is *not* designed to defend against an attacker who already controls your shell: anyone who can set `PADDOCK_*` environment variables or pass CLI flags can already run arbitrary commands, so paddock trusts those inputs by default.

Environment variables (`PADDOCK_*`) and CLI flags are therefore **permitted by default** — reaching for either already requires control of the invoking shell. `env` and `cli` can still be restricted or disabled through the allowlist when you want them to be — see [The allowlist](#the-allowlist).

> [!CAUTION]
> **Running paddock in CI**
>
> Continuous-integration runners are the one place where these two worlds overlap — the checked-in files and the process environment are often shaped by the same, potentially untrusted, pull request. If you run paddock in CI against untrusted branches, gate `env` (and `cli`) explicitly rather than relying on their permissive defaults.

## Enabling project-level config

Project-level config is **off by default (blocked)**. Grant it the narrowest set of keys the project needs, for that project only, in your user config — the file paddock reads, described under [Overview](#overview). If `XDG_CONFIG_HOME` points somewhere other than `~/.config` and your config is still at `~/.config/paddock/config.toml`, move it to `$XDG_CONFIG_HOME/paddock/` first rather than starting a new file there, or paddock will stop reading the old one:

```toml
[projects."/Users/alice/code/widgets".config.allowlist]
project_toml = ["volumes"]
```

A grant directly under `[config.allowlist]` applies to every repository you run paddock from. The project file keeps the lowest [weight](#precedence), so it can't override a value you set, but `volumes` and `build.args` merge per entry, so a granted file adds to yours, and `agents` merges per agent, so it can configure any agent you have not. Weigh what each key hands a committed file, and whoever can write that file: under the `opencode` agent that includes the agent itself, for every project its server mounts read-write, so a grant there is a grant to the agent. See the caution under [What the agent can reach](agents/opencode.md#what-the-agent-can-reach).

- `build.dockerfile` / `build.context` — paddock runs `docker build` on the host, from the project's Dockerfile and context.
- `volumes` — any existing host path, including `~`-relative ones expanded against *your* home (`~/.ssh`, say), mounted `rw` if the mapping says so.
- `agent` — selecting `claude` mounts your `~/.claude` read-write, plus `~/.claude.json` if it exists. The file can also choose an agent's [server](configuration.md#agentsnameserver), which starts a long-lived container from your server settings — your image, your mounts, your port — that keeps running after the project's own container exits. It cannot change those settings.
- `agents` — arguments for any agent you have set none for yourself; see the caution under [The allowlist](#the-allowlist).
- `network` — including `host`.

`project_toml = true` permits every key. Granted globally, it is the same decision as ticking "I trust this project" when an IDE or coding agent opens a repository, taken once for every repository at once. Reserve it for repositories you would run a script from.

```toml
[config.allowlist]
project_toml = true
```

For the key names a list may contain, see [The allowlist](#the-allowlist); for how per-project grants combine with global ones, see [Per-project overrides](#per-project-overrides).

## Per-project overrides

The `[projects."<absolute-path>"]` section lets you apply different settings to a specific project — including a project-specific allowlist that overrides your global one.

```toml
[projects."/Users/alice/code/widgets"]
image = "widgets-dev:latest"

[projects."/Users/alice/code/widgets".config.allowlist]
project_toml = ["volumes"]
```

In this example:
- When paddock runs from `/Users/alice/code/widgets`, it uses `widgets-dev:latest` as the base image.
- Project-level config is permitted, but only the `volumes` key — not `image`, `network`, or anything else.

A per-project rule replaces your global rule for that source rather than adding to it, so name every key the project needs.

**Note:** project paths must be **absolute** and match the *resolved* workdir exactly. paddock resolves the workdir — making it absolute and following symlinks — before both the `[projects]` lookup and the mounts, so the key must be the real path, not a symlinked one. Tilde expansion (e.g. `[projects."~/code/widgets"]`) is not yet supported, and paddock stops with an error naming such a key — follow [todofixthis/filters#92](https://github.com/todofixthis/filters/issues/92) for updates.

## The allowlist

The allowlist is more than the switch that turns project config on — it is the single mechanism for controlling **every** gated source: project files (`project_toml`), environment variables (`env`), and CLI flags (`cli`). Enabling `project_toml` and restricting `env` are two applications of the same rule, not separate features.

The remaining sources — `user` and `project_overrides` — have no allowlist entry and cannot be gated. Each is your own file, so there is no untrusted party to defend against; listing one in `[config.allowlist]` is rejected as an unknown key.

Each gated source has an entry in `[config.allowlist]`. Valid values are:

| Value | Effect |
|---|---|
| `true` | The source may contribute any config key. |
| `false` | The source is completely blocked. |
| `[]` (empty list) | Same as `false` — nothing is permitted. |
| `["image", "build.dockerfile"]` | Only the listed keys are permitted; dotted paths descend into nested tables. |

`agents` is a single key: it covers every agent's settings, and no dotted path narrows it to one agent.

> [!CAUTION]
> **Allowlisting `agents` lets a project file pass arguments to your agents**
>
> An argument can switch off an agent's own safeguards (Claude Code's
> `--dangerously-skip-permissions`, for one), and for the shell agent, `false`, the
> arguments are a command: `["-c", "…"]` runs it. Allowlist `agents` only for a
> project whose files you trust as much as your own config. `project_toml = true`
> includes it; to grant everything else, list the other keys, named under
> [`config.allowlist`](configuration.md#configallowlist).
>
> Your own `extra_args` for an agent, even `[]`, takes precedence over the project
> file's, but only for that agent, and only if you set `extra_args` itself: a bare
> `[agents.claude]` header protects nothing. A file also granted `agent` can choose
> which agent runs, the shell included, so the agent you normally use is no guide to
> which settings matter.

List entries are validated against the known config key paths, listed under [`config.allowlist`](configuration.md#configallowlist). An unknown path (e.g. a typo like `"imgae"`) is rejected when the user config is loaded.

**Validation runs before filtering.** An enabled source is validated as a whole, and only then does the allowlist project it down to the permitted keys. An invalid value in a key the rule would have dropped still aborts the run: under `project_toml = ["volumes"]`, a project file containing `image = ""` fails with `[project_toml:image] Non-empty value expected.` A malformed project file therefore aborts the run for every operator who has opted in, however narrow their grant.

To disable env-var overrides entirely:

```toml
[config.allowlist]
env = false
```

To let the command line contribute only `image`:

```toml
[config.allowlist]
cli = ["image"]
```

Flags that carry no config key — `--dry-run`, `--quiet`, `--version`, `--workdir` — keep working regardless.

## Precedence

The project file has the lowest weight of any source; see [Precedence](configuration.md#precedence) for the full order and how values merge.

**Example:** your user config sets `image = "ubuntu:26.04"`. A project's `.paddock/config.toml` sets `image = "widgets-dev:latest"`. Because `project_toml` (weight 10) is merged before `user` (weight 20), the user config wins — `ubuntu:26.04` is used, regardless of the project file.

To set the image for one project, put it in a per-project override in your user config instead:

```toml
[projects."/Users/alice/code/widgets"]
image = "widgets-dev:latest"
```

Project overrides (weight 30) are merged after user defaults (weight 20), so they win on conflict.

## The `.paddock` directory

When project-level config is enabled, paddock:

1. Creates `.paddock/` in the project workdir if it does not already exist.
2. Mounts it into the agent's container at the same absolute path, **read-only** by
   default. An agent with a server runs its tools in the server, which reaches the
   directory through its own mounts: read-write under `opencode`, whose server must
   mount the workdir read-write; see the
   [`opencode` agent](agents/opencode.md#what-the-agent-can-reach).
3. After the container exits, removes `.paddock/` — but only if paddock created it and it is still empty. If it has contents, paddock logs a warning and leaves the directory in place for you to inspect.

A `.paddock` that is a symlink is rejected rather than followed:

```
<path> is a symlink; paddock will not mount a symlinked project config directory
```

When project-level config is *disabled*, none of this happens: paddock leaves any `.paddock` file, directory, or symlink alone and makes no mount.

To allow the agent to write files into `.paddock/` (e.g. to persist state between runs), disable read-only mounting:

```toml
# Global — applies to all projects
[config]
project_dir_readonly = false
```

Or per-project:

```toml
[projects."/Users/alice/code/widgets".config]
project_dir_readonly = false
```

## Warning behaviour

paddock reports config it ignores with three warnings at `WARNING` level. The first two come from the allowlist.

A gated source (`project_toml`, `env`, or `cli`) contributed keys the rule does not permit — whether the source is wholly or partly disabled:

```
<source>: dropped non-allowlisted keys <paths> — add them to [config.allowlist].<source> to keep them
```

`<paths>` lists the dotted leaf paths dropped (`image`, `build.dockerfile`), with `agents`, `volumes` and `build.args` reported as single paths rather than one entry per mapping.

A source that is disabled failed validation — malformed TOML, an unknown key, or a bad value. Its errors are discarded with it rather than aborting the run, and it contributes nothing, so no keys are dropped:

```
<source> source had errors but is disabled by [config.allowlist] — ignored
```

An enabled project file set a key that only your user config may set: `config`, `projects`, or an agent server's settings. No grant can keep it, so paddock removes it before validating the file, and nothing under it can stop the run:

```
project_toml: ignored <key> — only your user config may set it
project_toml: ignored agents.<name>.server — server settings are read only from the global section of your user config
```

All three are intentional: paddock loads every source unconditionally so it can warn you when config is being silently dropped. A disabled project file that holds nothing but these user-only keys is the one case that draws no warning: paddock ignores a disabled file whole.

`--quiet` disables all logging, these warnings included; fatal config errors still print.

## Troubleshooting

For errors not specific to project config, see
[Troubleshooting](configuration.md#troubleshooting) in the configuration reference.

**`[project_toml] This value is not valid TOML.`**

The project file (`<workdir>/.paddock/config.toml`) does not parse. It aborts the run for anyone who has opted in — see [The allowlist](#the-allowlist).

**`project_toml: ignored config — only your user config may set it`**

The project file sets `[config]` (or `projects`), which only your user config may set. paddock ignores the section and carries on: a committed file cannot grant itself access, nor stop your run by trying. If the file is yours, move the section to your user config. If it is not, treat it as a reason to look at what else the file sets.

**`[project_toml:volumes.<path>] Path '<path>' does not exist or cannot be resolved (checked …).`**

A host path in the project file doesn't exist on this machine. A relative path resolves against the workdir, not `.paddock/`; see [Validation](configuration.md#validation).

**`<path> exists but is not a directory; paddock cannot mount it as the project config directory`**

A file named `.paddock` exists in the project workdir. Rename or remove it, then run paddock again.

**`project_toml: dropped non-allowlisted keys ... — add them to [config.allowlist].project_toml to keep them`**

Every key in the project file was dropped: no grant for `project_toml` applies to this run — it is off by default (blocked) — or the grant names none of the keys the file sets. If you granted it under `[projects."<path>".config.allowlist]`, check that `<path>` is exactly the resolved workdir: not a symlink, and not a parent of the directory you ran paddock from (see the note under [Per-project overrides](#per-project-overrides)). The `--workdir=` in the `docker run` line paddock prints is the path to match. See [Enabling project-level config](#enabling-project-level-config).

**Project config is loaded but some keys are ignored**

The allowlist is restricting which keys the project config may contribute. Check `[config.allowlist].project_toml` in your user config and any per-project `[projects."...".config.allowlist]` entry.
