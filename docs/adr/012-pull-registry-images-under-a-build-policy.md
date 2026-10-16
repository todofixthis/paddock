---
status: Accepted
date: 2026-10-16
scope: [docs/usage/, src/paddock/__main__.py, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/docker/build.py, src/paddock/docker/pull.py]
summary: A build table without build.dockerfile makes paddock pull image on build.policy's schedule (a Dockerfile, where set, still builds with ADR 011's label), timing pulls from a paddock-owned state file under XDG_STATE_HOME rather than .Metadata.LastTagTime or a pull on every run, and stopping when a due pull fails, as docker run --pull does, rather than running the local copy; no separate opt-in key.
revisit-when: Docker records a reliable last-pull time on every image store paddock supports; a project needs a build policy without a Dockerfile to mean something other than pulling; redundant pulls prove costly, through registry rate limits or drift across several Docker daemons; due pulls failing offline block work often enough that users need a fallback to the local copy.
---

# 012: Pull Registry Images Under a Build Policy

## Context

[ADR 011] left an image's dependency freshness to its Dockerfile, and among the fixes the
user docs give is building the image on a schedule in CI and pushing it to a registry. A
user of such an image sets `image` to its registry tag. Docker pulls that tag only when no
local copy exists, so the image paddock runs goes stale until the user remembers to run
`docker pull`. `build.policy` can't help: without `build.dockerfile` it is a config error.

This meets ADR 011's revisit trigger: "paddock gains a way to keep an image current other
than building it locally, such as pulling a registry-hosted image under a build policy".

Checked against Docker 29.8 on 2026-10-16:

- With the registry unreachable and a local copy present, `docker run --pull=always`
  exits 125 and doesn't fall back to the local copy.
- `.Metadata.LastTagTime` moves on every successful pull, unchanged ones included, on the
  containerd image store. On the classic store (overlay2) it stays at `0001-01-01` after a
  pull.
- A label lives in the image config, so paddock can't stamp one on a pulled image, as it
  does on a build, without building.
- No local signal tells whether a tag came from a registry: on the containerd store a
  purely local build gets `RepoDigests` too.

## Options

### Option 1: Do nothing

**Pros:** No change; `docker pull` stays explicit.
**Cons:** Keeping current stays manual.

### Option 2: Pull on the policy's schedule, timed from a state file (Accepted)

paddock records each successful pull's time in `$XDG_STATE_HOME/paddock/pulls.json`,
keyed by image reference as configured, and pulls when the image is missing locally or
the policy says the last pull is too old. An image present with no record counts as
pulled long ago, so the periodic policies pull it at once.

**Pros:** Works the same on every image store. A run that isn't due costs a local
`docker image inspect`; a due pull that finds nothing new, one registry round trip.
**Cons:** A second store beside Docker's (ADR 011's Option 5), which drifts: from pulls
paddock didn't make, between machines sharing a daemon, and between daemons sharing a
machine.

### Option 3: Pull on the policy's schedule, timed from `.Metadata.LastTagTime`

**Pros:** No state of its own.
**Cons:** On the classic store the zero time reads as missing, so `daily` and `weekly`
pull on every run. A `docker tag` resets it too.

### Option 4: Pull on every run

paddock passes `--pull=always` to `docker run` whenever a policy is set, with no schedule.

**Pros:** No state; always current.
**Cons:** Every run pays a registry round trip and fails offline, so `daily` and `weekly`
would mean nothing for pulls.

## Decision

Option 2. The policies already define a schedule, and a schedule needs a last-pull time
Docker doesn't reliably keep. Option 3 would make a classic-store user's `daily` silently
mean `always`, the failure ADR 011 fixed for builds. The state file's drift, the reason
ADR 011 rejected it for builds, costs at most a redundant pull here, or a stale image for
one period on a second daemon: a removed image reads as missing and pulls anyway.

ADR 011's reasons for the label stand, so builds keep it and the two paths measure age
differently: a build stamps its time on the image it makes, while a pull has nowhere on
the image to record one.

Pulling is what a `build` table without a Dockerfile means, rather than something a
separate key opts into. Every such config is an error today, so no working config changes
meaning, and a key would only add a way to set a policy that does nothing. A user wanting
pulling in one project only sets the policy under that project's
`[projects."<workdir>".build]` rather than in the user-level `[build]` or an exported
`PADDOCK_BUILD_POLICY`, which outweighs every file. A Dockerfile,
where one is set, still wins.

A due pull that fails stops paddock with Docker's error and `docker pull`'s exit status,
matching `docker run --pull`,
rather than running the local copy with a warning, since that copy may be the stale image
the policy exists to replace. `--build-policy=if-missing` runs the local copy for that
run.

## Consequences

- `build.dockerfile` is optional. `build.args` and `build.context` are ignored when
  pulling, so a user-level `args` doesn't break a project whose image is pulled. A
  `build` table holding only those pulls under the default `if-missing`, as `docker run`
  would anyway.
- A user-level policy pulls every project's `image` that has no Dockerfile, including a
  tag only ever built locally. Having no record, it is due at once, and a failed pull
  records nothing, so every run fails; where the name exists on a registry the user
  doesn't control, the pull instead replaces the local build with that image. The user
  docs must say so, and that `[projects."<workdir>".build] policy = "if-missing"` opts a
  project out of a user-file policy. A `.paddock/config.toml` can't: it weighs less than
  the user file. Nothing but `--build-policy` opts out of an exported
  `PADDOCK_BUILD_POLICY`.
- A user-level `build.dockerfile` makes every project build, so no project can pull,
  since no source can unset a lower one's Dockerfile.
- `if-missing` pulls before `docker run` would, so the pull's output and any failure
  arrive before the container starts. `--dry-run` neither pulls nor records anything.
- The state file is keyed by reference as written, not normalised, so `ubuntu` and
  `docker.io/library/ubuntu:latest` are timed separately. It follows the user config's
  XDG rules: an unset, empty or relative `XDG_STATE_HOME` falls back to `~/.local/state`.
  It is written atomically (a temporary file renamed over it), so concurrent runs can
  lose each other's entry, costing a pull, but never corrupt it. A corrupt or unreadable
  file reads as empty, and a failed write warns and lets the run go on, each costing a
  redundant pull.

[ADR 011]: 011-track-build-time-in-an-image-label.md
