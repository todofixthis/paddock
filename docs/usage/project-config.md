# Project-Level Configuration and the Allowlist

## Overview

paddock supports three levels of file-based configuration:

- **User-level** (`~/.config/paddock/config.toml`) — your personal defaults, applied to every project.
- **Project-level** (`.paddock/config.toml` in the project workdir) — settings committed alongside a project and shared with everyone who works on it.
- **Extra** (`--config-file` / `PADDOCK_CONFIG_FILE`) — an additional file, named explicitly at run time, that overrides both of the above. Handy for one-off runs and for CI, where the config file is chosen by the invoking command rather than found on disk.

The extra file has the same shape as your user config, but only its standard global fields (`image`, `network`, and friends) are applied — a `[projects]` or `[config]` section inside an extra file is ignored. If the named file does not exist, paddock carries on without it.

Because project-level config lives inside a project repository, paddock treats it as **untrusted by default**. A malicious or misconfigured project could otherwise redirect your Docker image, override your network settings, or mount sensitive paths. You must explicitly grant each project (or all projects) permission to contribute config before paddock will honour it.

The other two levels are trusted: your user config is yours, and an extra file is only ever loaded because you pointed paddock at it.

### What this protects against

The threat model is an **untrusted change landing in a repository** — a `.paddock/config.toml` committed by another contributor (or pulled in by an automated dependency update) that silently changes how your container runs. It is *not* designed to defend against an attacker who already controls your shell: anyone who can set `PADDOCK_*` environment variables or pass CLI flags can already run arbitrary commands, so paddock trusts those inputs by default.

Environment variables (`PADDOCK_*`), CLI flags, and the extra config file are therefore **permitted by default** — reaching for any of the three already requires control of the invoking shell. `env` and `cli` can still be restricted or disabled through the allowlist when you want them to be — see [The allowlist](#the-allowlist). The extra config file cannot be restricted: pointing paddock at one takes the very shell access the allowlist exists to defend, so gating it would buy nothing.

> **CI environments:** continuous-integration runners are the one place where these two worlds overlap — the checked-in files and the process environment are often shaped by the same, potentially untrusted, pull request. If you run paddock in CI against untrusted branches, gate `env` (and `cli`) explicitly rather than relying on their permissive defaults. Note that a pull request able to edit the CI command line can also pass `--config-file`, which no allowlist will stop — keep the paddock invocation itself under your control, not the branch's.

## Enabling project-level config

Add the following to your user config (`~/.config/paddock/config.toml`):

```toml
[config.allowlist]
project_toml = true
```

This globally permits any project's `.paddock/config.toml` to contribute configuration. If you prefer a narrower grant, see [The allowlist](#the-allowlist) below.

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

**Note:** project paths must be **absolute** and match the workdir exactly. Tilde expansion (e.g. `[projects."~/code/widgets"]`) is not yet supported — follow [phx-filters#92](https://github.com/phx-nz/phx-filters/issues/92) for updates.

## The allowlist

The allowlist is more than the switch that turns project config on — it is the single mechanism for controlling **every** gated source: project files (`project_toml`), environment variables (`env`), and CLI flags (`cli`). Enabling `project_toml` and restricting `env` are two applications of the same rule, not separate features.

The remaining sources — `user`, `extra`, and `project_overrides` — have no allowlist entry and cannot be gated. Each is your own file or your own invocation, so there is no untrusted party to defend against; listing one in `[config.allowlist]` is rejected as an unknown key.

Each gated source has an entry in `[config.allowlist]`. Valid values are:

| Value | Effect |
|---|---|
| `true` | The source may contribute any config key. |
| `false` | The source is completely blocked. |
| `[]` (empty list) | Same as `false` — nothing is permitted. |
| `["image", "build.dockerfile"]` | Only the listed keys are permitted; dotted paths descend into nested tables. |

List entries are validated against the known config key paths. An unknown path (e.g. a typo like `"imgae"`) is rejected when the user config is loaded.

To disable env-var overrides entirely:

```toml
[config.allowlist]
env = false
```

To restrict CLI flags to `--image` only:

```toml
[config.allowlist]
cli = ["image"]
```

## Precedence

Config sources are merged in ascending weight order — lower weight is merged first, higher weight wins on conflict:

| Weight | Source | Notes |
|---|---|---|
| 10 | `project_toml` | `.paddock/config.toml`; off by default |
| 20 | `user` | `~/.config/paddock/config.toml` |
| 30 | `project_overrides` | `[projects."..."]` section of user config |
| 40 | `extra` | `--config-file` / `PADDOCK_CONFIG_FILE` |
| 50 | `env` | `PADDOCK_*` environment variables |
| 60 | `cli` | Command-line flags |

**Example:** your user config sets `image = "ubuntu:22.04"`. A project's `.paddock/config.toml` sets `image = "widgets-dev:latest"`. Because `project_toml` (weight 10) is merged before `user` (weight 20), the user config wins — `ubuntu:22.04` is used, regardless of the project file.

To let the project config determine the image, use a per-project override instead:

```toml
[projects."/Users/alice/code/widgets"]
image = "widgets-dev:latest"
```

Project overrides (weight 30) are merged after user defaults (weight 20), so they win on conflict.

## The `.paddock` directory

When project-level config is enabled, paddock:

1. Creates `.paddock/` in the project workdir if it does not already exist.
2. Mounts it into the container at the same absolute path, **read-only** by default.
3. After the container exits, removes `.paddock/` — but only if paddock created it and it is still empty. If it has contents, paddock logs a warning and leaves the directory in place for you to inspect.

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

Whenever a gated source (`project_toml`, `env`, or `cli`) contributes config but is blocked by the allowlist, paddock logs a warning at `WARNING` level:

```
project_toml contributed config but project_toml is not in [config.allowlist] — ignored
```

This is intentional: paddock loads every source unconditionally so it can warn you when config is being silently dropped, rather than failing in unexpected ways or hiding the fact that a project file was present.

## Troubleshooting

**`ExceptionGroup: config validation failed` / `[user:...] ...`**

Your user config contains invalid TOML or a value that fails schema validation. Run paddock with a minimal user config to isolate the problem. Common causes:

- A typo in a key name (e.g. `imgae` instead of `image`).
- An unrecognised allowlist source key (only `cli`, `env`, and `project_toml` are valid).
- An allowlist value that is neither `true`, `false`, nor a list of strings.

**`[final:image] Non-empty value expected`**

No source supplied a Docker image. Set `image` in your user config or pass `--image` on the command line.

**`.paddock exists but is not a directory`**

A file named `.paddock` exists in the project workdir. Rename or remove it, then run paddock again.

**Project config is loaded but some keys are ignored**

The allowlist is restricting which keys the project config may contribute. Check `[config.allowlist].project_toml` in your user config and any per-project `[projects."...".config.allowlist]` entry.
