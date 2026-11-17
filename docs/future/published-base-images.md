# Publish Paddock's Base Images

Paddock ships Dockerfiles, one per bundled agent (ADR 022), and every user builds their
own image from one. That costs a first run several minutes, needs a checkout of the
repository or a copy of the file, and leaves each user's image as stale as their last
build.

## Suggested change

Build each bundled Dockerfile in CI and push the image to GitHub Container Registry,
tagged by paddock version and by the agent version it pins. A user sets `image` to one
and builds nothing; a user who needs more starts their own Dockerfile `FROM` it.

## Open questions

- Tags: by paddock release, by agent version, by date, or some of each, and what
  `latest` means when Renovate bumps a pin between releases.
- Whether a bundled server could then default to a published image. ADR 021 gives
  OpenCode's none because any default lacks the user's toolchain; a published image
  lacks it too.
- Whether the per-agent Dockerfiles then build `FROM` a published toolchain base,
  which ADR 022 rejected only for want of a registry to hold one.
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
