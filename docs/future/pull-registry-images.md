# Pull Registry Images Under a Build Policy

Let `build.policy` keep a registry-hosted `image` current by pulling it, with no local
Dockerfile, so a CI-built image (see "Stale installs" in `docs/usage/docker-images.md`)
updates without a manual `docker pull`.

## Motivation

The recommended fixes for stale installs pin versions in the Dockerfile and build the
image on a schedule in CI. Users of such an image set `image` to its registry tag and
drop `[build]`. Docker then pulls the tag only when no local copy exists, so the image
paddock runs goes stale until the user runs `docker pull` by hand.

## Design sketch

- `image` names a registry tag and `build.policy` is set, but `build.dockerfile` is not:
  paddock pulls instead of building, on the same schedule the policy already defines.
- Age comes from when paddock last pulled, not the image's `.Created`, which is when CI
  built it.
- `docker pull` of an unchanged tag is cheap, so a due pull that finds nothing new costs
  one registry round trip.

## Open questions

- Where does last-pull time live? paddock can't stamp a label on a pulled image (labels
  live in the image config, so adding one takes a build). `.Metadata.LastTagTime` moves
  on an unchanged pull on the containerd store and may answer this with no state;
  paddock-owned state is the fallback. ADR 011 weighs both for builds.
- Or skip the schedule: `docker run --pull=always` checks the registry on every run.
  Weigh its per-run latency and offline failure against tracking age.
- Today, setting `build.policy` without `build.dockerfile` is a config error. Does pulling
  become the meaning of that combination, or does it need an explicit opt-in?
- A failed pull (offline, registry down) with a local copy present: run the local copy
  with a warning, or stop?
- How does this interact with a user-level `[build]` and a per-project `image` (the
  warning in `build.dockerfile`'s docs)? If a `policy` without a `dockerfile` implies
  pulling, a user-level one would turn pulling on for every project's `image`.
