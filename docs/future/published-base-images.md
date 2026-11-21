# Publish Paddock's Base Images

Paddock ships Dockerfiles, one per bundled agent (ADR 022), and every user builds their
own image from one. That costs a first run several minutes, needs a checkout of the
repository or a copy of the file, and leaves each user's image as stale as their last
build.

## Suggested change

Build each bundled Dockerfile in CI and push the image to GitHub Container Registry. A user sets `image` to one
and builds nothing; a user who needs more starts their own Dockerfile `FROM` it.

## Structuring the Dockerfiles for those who pull them

A published image is downloaded layer by layer, and a client fetches again every layer
that changed and every layer after it. What follows was learnt publishing images from a
sibling repository (`todofixthis/config-paddock#83`), where it took about 60% of pin
bumps from a full download to a download of the last few layers.

- **Keep each pin beside the step that uses it.** Docker passes an `ARG` to every `RUN`
  after its declaration, so pins gathered at the top rebuild every layer on any bump.
  The bundled Dockerfiles already do this (checked here on Docker 29.9.2: with the
  `ARG` at the top, changing it reran an earlier `RUN` that never read it; declared
  beside its step, the earlier `RUN` stayed cached). Renovate needs only the annotation
  on the line above the `ARG`.
- **Order steps by what depends on what, then by how often each is bumped**, rarest
  first, so the layers that change most are the last and smallest to fetch again. Count
  bumps per pin from the full history: a shallow clone undercounts without saying so.
  Compare only pins that existed for the whole window, and judge a newer one by its
  upstream's release cadence.
- **Leave no installer cache in a layer.** There, uv's cache was a second copy of each
  tool it installed, about 330 MB for one of them. Whether `npm install -g` leaves a
  copy worth removing in these images has not been measured.
- **A shared base makes every base bump a full download.** Each image built `FROM` a
  common baseline had all its own layers rebuilt whenever a baseline pin moved. Weigh
  that against ADR 022's repeated steps before introducing one.
- **A scheduled rebuild without cache is a full download for everyone.** It is the price
  of fresh apt packages, and sets how often that price is paid.
- **Reordering steps is itself a full download**, once, so settle the order before the
  first publish.

## Open questions

- Tags: by paddock release, by agent version, by date, or some of each, and what
  `latest` means when Renovate bumps a pin between releases.
- Whether a bundled server could then default to a published image. ADR 021 gives
  OpenCode's none because any default lacks the user's toolchain; a published image
  lacks it too.
- Whether the per-agent Dockerfiles then build `FROM` a published toolchain base,
  which ADR 022 rejected only for want of a registry to hold one, given what a shared
  base costs those who pull (above).
- What the published `claude` image is: `claude.Dockerfile` installs no agent unless
  built with `AGENT=claude`, and whether the toolchain-only image it builds by default
  is published too.
- Whether CI then builds only the file that changed; today a change to either rebuilds
  every image.
- How long old tags are kept.
- Platforms: `linux/amd64` alone, or `linux/arm64` too for Apple silicon.
- What rebuilds an image whose apt packages have gone stale without any pin moving
  (ADR 016 leaves apt unpinned).
- Provenance and signing, and who may push.
- How `build.policy` treats a published image: it already pulls an image with no
  Dockerfile (ADR 013).

## Why deferred

ADR 016's revisit trigger names this ("paddock publishes the bundled image to a
registry") and nothing has needed it yet. Splitting the Dockerfile per agent (ADR 022)
is the groundwork: each file is the unit an image would be built from.
