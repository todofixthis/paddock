# Volume Container Path Validation

The `Volume` filter validates the mode suffix (`:ro`/`:rw`) but does not require the
path portion to be absolute. Relative paths (e.g. `"data:ro"`) and empty paths
(e.g. `""`) pass through silently; Docker rejects both at runtime.

## Suggested fix

Add a leading-slash check after the colon split in `Volume._apply`, before the mode
suffix check, and emit a new `CODE_INVALID` error (or a dedicated code) when the path
portion does not start with `/`.

## Why deferred

Surfaced during code review of the `filepath-filter` branch. Fixing it was out of
scope for that branch; noted here so it is not lost.
