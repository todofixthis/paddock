---
status: Accepted
date: 2026-10-13
scope: [docs/usage/, src/paddock/docker/build.py]
summary: Measure an image's age for the daily and weekly build policies from a paddock.built-at label that every paddock build stamps, falling back to .Created, rather than from .Created alone or .Metadata.LastTagTime; paddock's builds keep the layer cache (no --no-cache), leaving installed dependencies' freshness to the Dockerfile, as the user docs describe.
revisit-when: the documented Dockerfile fixes prove insufficient and paddock takes on dependency freshness itself; Docker exposes a reliable last-build time of its own; .Metadata.LastTagTime is adopted for another path, such as pulls, making one mechanism for both worth weighing.
revisit-discharged-by: [13]
---

# 011: Track Build Time in an Image Label

## Context

[`ImageBuilder`] rebuilds under `daily` and `weekly` once the image's `.Created` time
passes the policy's age limit. Checked against Docker 29.8 (BuildKit, containerd image
store) on 2026-10-13:

- A fully cached build leaves `.Created` unchanged. An uncached build resets it, but only
  if it adds a layer: one that only sets metadata (`ENV`, `LABEL`) inherits its base's
  `.Created`.
- `SOURCE_DATE_EPOCH`, in the environment or as a build arg, pins `.Created` to that time.
- A `--label` given to `docker build` lands in the image's config whatever `.Created`
  says, without invalidating any cached layer.
- `.Metadata.LastTagTime` moves on every tag operation: a fully cached build, and also a
  `docker pull` or `docker tag`.

So once an image passes the age limit, every run rebuilds it, quickly and from cache,
without moving `.Created`, until some layer changes.

A second problem sits beside this one. The bundled [`images/Dockerfile`] installs the agent
in an unpinned `RUN npm install -g @anthropic-ai/claude-code` layer, which the cache
replays, so no cached rebuild updates the agent. That is a property of the Dockerfile,
not of how paddock measures age.

## Options

### Option 1: Do nothing

**Pros:** No change.
**Cons:** A stale image rebuilds on every run until a layer changes, which for the bundled
Dockerfile is never.

### Option 2: Stamp a build-time label on every build (Accepted)

`docker build` gets `--label paddock.built-at=<UTC time>`, and age is read from that
label, falling back to `.Created` for an image paddock didn't build.

**Pros:** Measures what the policies mean, when paddock last built the image, whatever
the image's layers or `SOURCE_DATE_EPOCH` say. Leaves the cache, and build times, as
they are.
**Cons:** Fixes the rebuild loop only; a cached rebuild still updates nothing the
Dockerfile leaves unpinned.

### Option 3: Build the periodic policies without the layer cache

`daily` and `weekly` pass `--no-cache --pull`, which resets `.Created` and refreshes every
layer.

**Pros:** Also refreshes unpinned installs and the base image.
**Cons:** Turns each periodic rebuild into a full build taking minutes, and needs network
access a cached build doesn't, so offline runs fail without a fallback. Breaks for a
`FROM` image that exists only locally. Still loops for a Dockerfile adding no layer, or
built with `SOURCE_DATE_EPOCH`.

### Option 4: Read age from `.Metadata.LastTagTime`

**Pros:** Needs no label or state, and also moves when a registry image is pulled.
**Cons:** Measures the last tag operation, not the last build: a `docker tag` or a pull
resets it as well. Untested on Docker's classic image store, and Docker doesn't document
it as a build time.

### Option 5: Record build times in a paddock-owned state file

paddock writes each image's build time to a file under the user's home directory.

**Pros:** Leaves the image untouched.
**Cons:** A second store to keep in step with Docker's: removing or retagging an image
leaves a stale entry, and the file means nothing on another machine sharing the daemon.

## Decision

Option 2. The label fixes the rebuild loop at its cause, `.Created` measuring the wrong
thing. It records exactly what the policies mean and travels with the image, so it goes
when the image goes. Option 4 would give nearly the same answer for a locally built tag,
but rests on a field Docker doesn't document as a build time and that is untested on the
classic store; the label is a record paddock writes and owns. Option 5 gets the label's
measurement at the cost of a store that drifts from Docker's.

Option 3 is rejected as out of scope rather than as a rival fix. It answers a different
question, how current an image's dependencies are, and even as a fix for the loop it
fails for some Dockerfiles. Dependency freshness belongs to the Dockerfile, where its author controls it,
so the user docs set out the fixes instead: pin versions and let a tool such as Renovate
bump them, build on a schedule in CI, or bust the cache for an install that must stay
unpinned.

## Consequences

- `daily` and `weekly` rebuild once per period again, from cache, in seconds.
- Those rebuilds still don't update an unpinned install. The user docs must say so and
  give the fixes, since the policy names suggest otherwise.
- Every build gets a new image ID. Cached builds already did on Docker 29.8's
  containerd store, so there the label adds no churn of its own; the classic store is
  untested.
- ~~A pulled image can't carry a label paddock stamps, so pulling under a build policy
  (the revisit trigger) would need Option 4 or 5 for that path.~~ Spent by
  [ADR 013], which times pulls with Option 5.
- Labels are inherited, so an image built `FROM` a paddock-built image carries its base's
  `paddock.built-at` until paddock builds it.

[ADR 013]: 013-pull-registry-images-under-a-build-policy.md
[`ImageBuilder`]: ../../src/paddock/docker/build.py
[`images/Dockerfile`]: ../../images/Dockerfile
