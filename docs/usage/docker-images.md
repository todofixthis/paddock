# Custom Docker Images

paddock runs any image, but assumes a few things about how it starts. This page covers
what a custom image needs, a recommended entrypoint, and diagnosing one that won't start.

## How paddock runs an image

paddock prints the command before running it (unless `--quiet`). Abridged:

```
docker run --rm -it --name paddock-<dir>-<agent> --workdir=<workdir> \
  -v <workdir>:<workdir>:rw <other volumes> [--network <network>] <image> <command>
```

`<command>` is the agent's command (`claude` for the `claude` agent, `/bin/bash` for
`false`). A command before `--` replaces it (`paddock /bin/bash`); with none, arguments
after `--` extend it (`paddock -- --continue` runs `claude --continue`). paddock never
passes `--entrypoint`, so the image's own `ENTRYPOINT`, if it has one, receives
`<command>` as its arguments.

A custom image therefore needs:

- **The command on `PATH`.** Without an `ENTRYPOINT`, Docker looks the command up
  against the image's `ENV PATH` alone: shell profiles don't run. The `false` agent
  needs `/bin/bash`.
- **An `ENTRYPOINT` that execs its arguments promptly**, if there is one. paddock
  attaches your terminal to the container, so an entrypoint that waits for something
  first leaves you at a blank screen.
- **A root user.** Agent config mounts to `/root` (e.g. `~/.claude` →
  `/root/.claude`), and `~` in container-side volume paths expands to `/root`.

The workdir mounts at the same absolute path as on the host, so paths in agent state
(e.g. Claude Code's per-project settings) match on both sides.

## Starting points

paddock ships a Dockerfile in `images/` that installs Python, Node.js and the selected
agent; see [Docker Image][docker-image]. Point [`build.dockerfile`](configuration.md#builddockerfile) at your
own Dockerfile to have paddock build it for you, or set
[`image`](configuration.md#image) to a prebuilt one.

## Stale installs

Docker caches each build step and replays it while the step, and every step before it,
is unchanged. A step that installs whatever is current, such as
`npm install -g @anthropic-ai/claude-code` or `apt-get upgrade`, runs once; every later
build reuses what it installed then. [`build.policy`](configuration.md#buildpolicy)'s
`daily` and `weekly` rebuild on schedule, but from that cache, so they never update such
an install. The bundled Dockerfile's agent step is one.

Three fixes, best first.

### Pin versions and let Renovate bump them

Pin each install to a version in an `ARG`. Bumping the `ARG` changes the step, so the
next build reruns it. In a copy of the bundled Dockerfile, the agent step becomes:

```dockerfile
# renovate: datasource=npm depName=@anthropic-ai/claude-code
ARG CLAUDE_CODE_VERSION=2.1.292

RUN case "$AGENT" in \
    claude) npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" ;; \
    none) echo "No agent selected" ;; \
    *) echo "Unknown agent: $AGENT" && exit 1 ;; \
    esac
```

[Renovate][renovate] then opens a pull request for each new release. It bumps the `FROM`
tag on its own; a regex manager reads the `# renovate:` comment above each `ARG`:

```json
{
  "customManagers": [
    {
      "customType": "regex",
      "managerFilePatterns": ["/Dockerfile$/"],
      "matchStrings": [
        "# renovate: datasource=(?<datasource>\\S+) depName=(?<depName>\\S+)\\nARG [A-Z0-9_]+=(?<currentValue>\\S+)"
      ]
    }
  ],
  "extends": ["config:recommended"],
  "packageRules": [
    {
      "description": "Track Claude Code's stable channel rather than latest, which moves almost daily",
      "followTag": "stable",
      "matchPackageNames": ["@anthropic-ai/claude-code"]
    }
  ]
}
```

Merging a bump changes your Dockerfile, not your image: pull the change, then run
`--build-policy=always` once, as after any Dockerfile edit. apt packages are impractical
to pin this way; the next fix covers them.

### Build on a schedule in CI

Build the image in GitHub Actions on a schedule, push it to a registry, and point
[`image`](configuration.md#image) at it with no `[build]` table. A hosted runner starts
with no layer cache, so every run reinstalls everything; if you add a cache, skip it on
scheduled runs:

```yaml
name: Publish image

on:
  push:
    branches:
      - main
  schedule:
    # Sundays at 14:00 UTC
    - cron: '0 14 * * 0'
  workflow_dispatch: {}

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: docker/login-action@v4
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v7
        with:
          context: .
          file: images/Dockerfile
          pull: true
          push: true
          # Image names must be lowercase
          tags: ghcr.io/your-name/your-image:latest
```

Docker pulls the image only when no local copy exists, so run
`docker pull ghcr.io/your-name/your-image:latest` to pick up a new build. GitHub makes a
package pushed this way private, so the pull needs `docker login ghcr.io` with a token
that has `read:packages`, unless you make the package public.

### Bust the cache for an install that must stay unpinned

Declare an `ARG` inside the stage, after `FROM`, just before the step. Docker reruns
every step after an `ARG` whose value changed, and keeps the cached steps before it. An
`ARG` above `FROM`, or none at all, busts nothing:

```dockerfile
ARG CACHE_BUST
RUN npm install -g @anthropic-ai/claude-code
```

Pass a value that changes once a day, for example through a shell alias, and keep
`build.policy` at `daily`:

```bash
alias paddock='paddock --build-args-CACHE_BUST="$(date +%F)"'
```

## Running commands through a login shell

Installers often put tools where only a shell profile adds them to `PATH`, such as
Claude Code's native installer (`~/.local/bin`). Other setup can live there too, like
starting an agent that exports a socket.

The simplest fix is `ENV PATH=...` in the Dockerfile, and the only one for an image
without bash. Where the profile does more than set `PATH`, run every command through a
login shell instead:

```dockerfile
ENTRYPOINT ["/bin/bash", "-lc", "exec \"$@\"", "paddock-entry"]
CMD ["/bin/bash"]
```

`bash -l` sources `/etc/profile` and `~/.bash_profile`, then `exec "$@"` replaces the
shell with paddock's command, so its exit status and signals pass straight through.
`paddock-entry` only fills `$0`.

Two things a login shell skips or undoes:

- **`~/.bashrc` doesn't run**, since the shell isn't interactive, and `~/.profile` doesn't
  either once `~/.bash_profile` exists. Put setup in `~/.bash_profile`, including any
  `PATH` line an installer wrote to `~/.bashrc`.
- **`/etc/profile` can reset `PATH`**, discarding directories the base image added with
  `ENV PATH`. Debian's does (e.g. `debian`, `oven/bun:*-debian`). Re-add them in
  `~/.bash_profile`.

## Troubleshooting

### paddock hangs with no output

paddock prints the `docker run` command, then nothing appears until you press ⌃C.
`docker logs` shows nothing either.

The image's `ENTRYPOINT` is waiting before it runs the command. Images built for another
runner often do this: [leash][] images' `leash-entry` polls for a ready file that only
the leash runner creates, so it waits forever under paddock. Check the entrypoint:

```bash
docker image inspect --format '{{json .Config.Entrypoint}}' <image>
```

To confirm, rerun the printed command with `--entrypoint <command>` (e.g.
`--entrypoint claude`) before the image name, and drop the command after it. If the
agent starts, or fails fast with the error below, the entrypoint was the problem. Build
an image without it, or with the login-shell entrypoint above.

### `exec: "claude": executable file not found in $PATH`

Docker couldn't find the command on the image's `ENV PATH`, usually because the image has
no `ENTRYPOINT` and the tool is only on `PATH` once a shell profile runs. Add its
directory with `ENV PATH`, or use the login-shell entrypoint above.

[docker-image]: https://phx-paddock.readthedocs.io/en/latest/#docker-image
[leash]: https://github.com/strongdm/leash
[renovate]: https://docs.renovatebot.com/
