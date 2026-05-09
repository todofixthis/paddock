# Container Home Path Configuration

The home directory inside the container is currently hardcoded as `CONTAINER_HOME =
"/root"` in `src/paddock/config/schema.py`. This is correct for images that run as
root, but breaks tilde expansion in container paths for non-root users.

## Suggested change

Add a top-level `container_home` config key (and a `PADDOCK_CONTAINER_HOME`
environment variable) to the configuration matrix. Pass the validated value to
`VolumeMap(container_home_dir=...)` in the config schema so that container-side tilde
expansion reflects the actual container user.

## Why deferred

No current use case requires a non-root container user. Surfaced when introducing
`CONTAINER_HOME` as a module constant; noted here so the path to making it
configurable is clear.
