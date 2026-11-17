# The `claude` Agent

Runs [Claude Code](https://claude.com/claude-code) in the container. It is the default
[`agent`](../configuration.md#agent), so a config that sets only an
[`image`](../configuration.md#image) with Claude Code installed is enough:

```toml
image = "paddock-claude:latest"
```

## What paddock runs

- **The command:** `claude`, followed by your
  [`extra_args`](#arguments-on-every-run) and anything after `--`. The image needs
  `claude` on its `PATH`; see [Custom Docker Images](../docker-images.md).
- **The container:** `paddock-<workdir name>-claude`, removed when Claude Code exits.
- **No server.** Claude Code runs whole in the one container, so none of the
  [`agents.<name>.server`](../configuration.md#agentsnameserver) settings apply to it.

## What persists between runs

paddock mounts two paths from your home directory, both read-write, so the container
shares your host's Claude Code state rather than keeping its own:

| Host | Container | Holds |
|---|---|---|
| `~/.claude` | `/root/.claude` | Claude Code's config directory, so settings and sign-in carry over. |
| `~/.claude.json` | `/root/.claude.json` | Onboarding and account state. |

`~/.claude.json` is mounted only if it exists as a file when paddock starts; until
then, runs start at onboarding.

The mount pins the file as it was when the container started, and Claude Code on the
host replaces the file on each save. Run both at once and the container reads stale
state, and what it writes to the file is lost.

## Building the image

When paddock [builds the image](../configuration.md#builddockerfile), it passes the
build argument `AGENT=claude`. The bundled `images/claude.Dockerfile` installs Claude
Code for that value, at the version its `CLAUDE_CODE_VERSION` argument pins; see
[Docker Image](https://phx-paddock.readthedocs.io/en/latest/#docker-image). A
[`build.args.AGENT`](../configuration.md#buildargs) of your own overrides it, and a
Dockerfile without `ARG AGENT` ignores it.

## Arguments on every run

Set arguments Claude Code should get on every run under `[agents.claude]`:

```toml
[agents.claude]
extra_args = ["--verbose"]
```

`paddock -- "fix it"` then runs `claude --verbose "fix it"`. Your arguments come before
anything after `--`, so don't end the list with an option whose value is optional, such
as `--resume`: Claude Code would take your prompt as its value. Pass those after `--`
instead: `paddock -- --resume`.

[`agents.<name>.extra_args`](../configuration.md#agentsnameextra_args) covers how
sources combine, how to clear the list for one project, and what a project file may
set.
