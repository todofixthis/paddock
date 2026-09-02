---
name: e2e-testing
description: Use when checking paddock end to end — a manual, smoke or integration check that runs the real `paddock` command against real Docker containers rather than unit tests — including in a Claude Code cloud session where no docker daemon is running and image pulls fail.
---

# E2E testing paddock

Run `.agents/skills/e2e-testing/scripts/preflight.sh` from the repo root first. It starts dockerd when none is running, pulls the base image, syncs the venv, and fails on any stray `PADDOCK_*` variable: an unknown name is a fatal config error, and a known one silently overrides the scenario's config, which is worse.
## Images

Only `mcr.microsoft.com` is reachable through the cloud egress proxy; Docker Hub, ECR Public and GHCR serve blobs from blocked CDN hosts. The base image is `mcr.microsoft.com/azurelinux/base/core:3.0` (`DEFAULT_E2E_IMAGE` in the preflight script). Build custom images `FROM` the base image, which needs no network, and tag them with a run-specific prefix.

## Invoking paddock

Run everything below from the repo root. Use `.venv/bin/paddock`, the editable install. Do not use `uv run paddock`: in cloud sessions it adds an unrelated uv deprecation warning to stderr.

Every scenario passes `--agent=false` and an explicit container command, one `bash -c '…'` after `--`. The exception is a scenario about an agent itself: without the flag the default agent is `claude`, which changes the container command to `claude` and mounts `~/.claude` read-write. Without a container command the shell agent runs an interactive `/bin/bash` that never exits under a pseudo-TTY.

Isolate each scenario in its own directory `$S` holding `home/` and a project directory. Give project directories basenames of `[a-z0-9-]` only: the basename goes into the container name, `paddock-<basename>-<agent-key>`, which paddock probes with `docker ps -a --filter name=^…$`, a regex, so a metacharacter silently makes the probe match nothing.

A dry run (`--dry-run`) prints the argv on stdout and log lines on stderr, and still runs `docker ps`. It runs the `.paddock` create-and-remove lifecycle only when the user config allowlists `project_toml`; by default it is never touched. Capture the streams separately when the scenario asserts which stream carried text.

A real run needs a pseudo-TTY because docker gets `-it`. `script` returns the wrapped exit status; the capture merges both streams with CRLF endings and may carry stray NUL bytes, so assert with `grep`.

```bash
S=/tmp/e2e/c1; mkdir -p "$S/home/.config/paddock" "$S/c1-project"
printf 'image = "mcr.microsoft.com/azurelinux/base/core:3.0"\nagent = false\n[config.allowlist]\nproject_toml = true\n' > "$S/home/.config/paddock/config.toml"
# dry run
env -i PATH="$PATH" HOME="$S/home" .venv/bin/paddock --workdir="$S/c1-project" --agent=false --dry-run >"$S/out" 2>"$S/err"; echo "exit=$?"
# real run
cat > "$S/run.sh" <<RUN
#!/bin/bash
env -i PATH="$PATH" HOME="$S/home" "$PWD/.venv/bin/paddock" --workdir="$S/c1-project" --agent=false -- bash -c 'grep " $S/c1-project/.paddock " /proc/mounts; touch $S/c1-project/.paddock/x || echo RO_OK'
RUN
chmod +x "$S/run.sh"; timeout 120 script -qec "$S/run.sh" /dev/null >"$S/out" 2>&1; echo "exit=$?"
grep -c "^RO_OK" "$S/out"; ls -d "$S/c1-project/.paddock" 2>/dev/null || echo "removed after exit"
```

## Asserting

The workdir mounts `rw` and `.paddock` mounts `ro`. Setting `config.project_dir_readonly = false` in the user config is the only way `.paddock` mounts `rw`.

A build runs only on a real run, never under `--dry-run`, and logs `Image build: triggered` or `Image build: skipped (up to date)`. Give `build.dockerfile` and `build.context` absolute paths in a scenario config; relative ones resolve against the cwd. Build output repeats each `RUN` line, so match the container's own output at line start (`grep "^extra="`) rather than counting a substring.

- Host state before and after: `.paddock` creation and removal, and files written through the workdir mount, which arrive root-owned.
- Exit status: paddock exits with docker's return code; a config error exits 1; `--dry-run` exits 0.
- Warnings and errors: grep the literal strings under `src/paddock`, not the docs.

## Cleanup

Remove only what the run created, guarding each against an empty list: `docker rm -f $(docker ps -aq --filter name=<prefix>)` and `docker rmi $(docker images -q --filter reference='<prefix>*')`. Never remove the base image; other sessions may share the daemon.
