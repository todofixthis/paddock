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
`false`). A command you pass after `--` replaces it rather than extending it, so name the
agent too: `paddock -- claude --continue`. paddock never passes `--entrypoint`, so the
image's own `ENTRYPOINT`, if it has one, receives `<command>` as its arguments.

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
agent; see the README's Docker Image section. Point `[build]` at your own Dockerfile to
have paddock build it for you, or set `image` to a prebuilt one.

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

[leash]: https://github.com/strongdm/leash
