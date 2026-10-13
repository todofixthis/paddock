---
status: Accepted
date: 2026-10-13
scope: [README.rst, docs/usage/, src/paddock/__main__.py, src/paddock/docker/build.py]
summary: The periodic build policies (daily, weekly) refresh on every build with --no-cache --pull, so need a pullable base, read age from a paddock.refreshed-at label each refresh stamps (falling back to .Created), and run the existing image if a refresh fails; the always and if-missing policies keep the layer cache.
revisit-when: Refresh failures persist across runs often enough that retrying every run without backoff costs users; a minutes-long refresh per period costs users enough that they drop the periodic policies or ask for faster refreshes; paddock gains per-image state for another reason.
---

# 011: Refresh Without the Layer Cache on Periodic Rebuilds

## Context

[`ImageBuilder`] rebuilds under `daily` and `weekly` once the image's `.Created` time
passes the policy's age limit, and runs a plain `docker build`. Checked against Docker
29.8 (BuildKit, containerd image store) on 2026-10-13:

- A fully cached build leaves `.Created` unchanged, as does `--pull` when the base image
  hasn't moved. An uncached build resets it, but only if it adds a layer: one that only
  sets metadata (`ENV`, `LABEL`) inherits its base's `.Created`.
- `SOURCE_DATE_EPOCH`, in the environment or as a build arg, pins `.Created` to that time.
- A `--label` given to `docker build` lands in the image's config whatever `.Created`
  says.
- A failed build leaves the existing tag pointing at the old image.
- `--pull` fails for a `FROM` image that exists only locally.

Two faults follow. The bundled [`images/Dockerfile`] installs the agent in an unpinned
`RUN npm install -g @anthropic-ai/claude-code` layer, which the cache replays, so a
periodic rebuild never updates the agent. And once the image passes the age limit, every
run rebuilds without moving `.Created`, until some layer changes.

Users pick `daily` or `weekly` to keep the agent and base image current. `always` serves
applying a Dockerfile edit, where the cache is what makes it quick.

## Options

Three questions sit apart from the cache choice, and don't rank the options below:
whether to `--pull` the base image, where age is read from, and what a failed refresh
does. Decision settles each.

### Option 1: Do nothing

**Pros:** No change; cached rebuilds are fast and work offline.
**Cons:** The periodic policies refresh nothing. Users must know to run
`docker build --no-cache` by hand.

### Option 2: Build periodic refreshes uncached (Accepted)

`daily` and `weekly` pass `--no-cache` on every build, the first included; `always` and
`if-missing` keep the cache.

**Pros:** Refreshes every layer of any Dockerfile.
**Cons:** A refresh reruns every layer: minutes, not seconds, once per period.
**Risks:** A failure that persists — offline, a registry rate limit, an upstream break the
cache used to hide, the user's own broken Dockerfile edit — is retried on every run with
no backoff, under the fallback below. A late failure costs each run most of a full build.

### Option 3: Bust only the agent layer with a paddock-supplied build arg

paddock passes a changing build arg (e.g. the date) that `images/Dockerfile` declares
just above the agent's `RUN`, so only that layer and those after it rerun.

**Pros:** Fast: the agent layer reruns, the apt and Node layers stay cached.
**Cons:** Refreshes only Dockerfiles that declare the arg; a custom Dockerfile silently
gets nothing. The apt and Node layers never refresh.

## Decision

Option 2. The periodic policies exist to pick up upstream changes, and only an uncached
build does that for every Dockerfile a user might bring; Option 3 reaches only the bundled
image's agent.

**Age comes from a `paddock.refreshed-at` label** that each refresh stamps, falling back
to `.Created` for an image no refresh built. An uncached build alone doesn't end the
rebuild loop: a Dockerfile adding no layer, or one built with `SOURCE_DATE_EPOCH`, keeps a
stale `.Created` however often it rebuilds, so every run would rebuild uncached. The label
records what the policy means — when paddock last refreshed — independent of what the
image contains. Only refreshes stamp it: a cached `always` build refreshed nothing, so its
image carries no label and age falls back to `.Created`, its newest layer's time.

**`--pull` goes with every refresh**, since the cache choice alone never updates the base
image. It breaks periodic policies for a Dockerfile built `FROM` a local-only image.
Retrying without it can't tell that failure from an upstream break, and would double the
cost of the latter; such a Dockerfile takes `always` or `if-missing` instead.

**A failed refresh falls back to the existing image**, with a warning, so the refresh
doesn't regress offline use, which a cached rebuild never broke: a stale agent beats no
run. With no image, the failure stops the run as before. The label can't record failed
attempts for backoff, since a failed build produces no image to carry it; paddock would
need state of its own, not worth adding until persistent failures prove common.

## Consequences

- One run per period starts minutes slower while every layer rebuilds.
- `always` is less fresh than `daily`: it rebuilds every run but never refreshes a cached
  layer. User docs must say so, and that periodic policies need a pullable base.
- A cached build that changes a layer, such as `--build-policy=always` after a Dockerfile
  edit, drops the label and resets `.Created`, so the next refresh counts from the edit:
  cached upstream layers can then be up to a period older than the policy implies.
- A refresh that falls due can't be put off once started; interrupting it loses the run
  rather than falling back. `--build-policy=if-missing` skips it for one run.
- A refresh that installs a broken upstream release replaces the tag; the old image is
  deleted or left dangling, depending on the image store, and nothing rolls it back.
  Users needing stability pin versions in their Dockerfile or use `if-missing`. On a store
  that leaves it dangling, each refresh adds a full unshared image until pruned.
- Two runs starting together on a stale image each run a full build, and the last to
  finish takes the tag. The window was seconds under the cache; now it is minutes.
- Labels are inherited, so a cached build `FROM` a paddock-refreshed image carries its
  base's `paddock.refreshed-at` until its own refresh replaces it.

[`ImageBuilder`]: ../../src/paddock/docker/build.py
[`images/Dockerfile`]: ../../images/Dockerfile
