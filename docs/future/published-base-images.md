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
sibling repository (`todofixthis/config-paddock#83`). There, pin placement and
reordering together took 29 of its baseline's 48 pin bumps in three months from nearly
a whole image to its last few layers; the figure is that repository's mix of bumps, not
a forecast for this one.

- **Keep each pin beside the step that uses it.** Docker passes an `ARG` to every `RUN`
  after its declaration, so pins gathered at the top rebuild every layer on any bump.
  The bundled Dockerfiles already do this (checked here on Docker 29.9.2: with the
  `ARG` at the top, changing it reran an earlier `RUN` that never read it; declared
  beside its step, the earlier `RUN` stayed cached). Renovate needs only the annotation
  on the line above the `ARG`.
- **Put first the steps others depend on and the heavy ones, then the rest by how often
  each is bumped, rarest first.** A heavy step that is also bumped often has no good
  place: put early it rebuilds everything after it, put late it is the large layer
  fetched most. There, two such steps were left early and account for the bumps that
  still rebuild most of the image. Here the agent's install is both the most bumped
  and likely the heaviest step after apt, and already comes last, after Python and
  Node.js, which it needs.
- **Count bumps per pin from the full history.** That repository's `AGENTS.md` has the
  command. A shallow clone undercounts without saying so: at depth 50 it found 48 of
  61. Compare only pins that existed for the whole window, and judge a newer one by its
  upstream's release cadence.
- **Measure what each installer leaves behind.** There, uv's cache was a second copy of
  one tool it installed, about 330 MB, and was removed; another uv step left almost
  nothing and was left alone. What `npm install -g` leaves in these images has not
  been measured.
- **A bump early in a shared base rebuilds every image built on it.** There, each
  flavour built `FROM` a baseline, so a baseline bump rebuilt every flavour's layers
  too. That is no worse than these Dockerfiles today, where a Python or Node.js bump
  already rebuilds the agent's layer; it is a reason to keep often-bumped pins out of
  a base, not a reason against one.
- **A scheduled rebuild without cache is a full download for everyone.** It is the price
  of fresh apt packages, and sets how often that price is paid.
- **Reordering steps is itself a near-full download**, once, so settle the order before
  the first publish.

## Open questions

- Tags: by paddock release, by agent version, by date, or some of each, and what
  `latest` means when Renovate bumps a pin between releases.
- Whether a bundled server could then default to a published image. ADR 021 gives
  OpenCode's none because any default lacks the user's toolchain; a published image
  lacks it too.
- Whether the per-agent Dockerfiles then build `FROM` a published toolchain base,
  which ADR 022 rejected only for want of a registry to hold one. The two images would
  then share their toolchain layers.
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
