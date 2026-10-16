---
status: Accepted
date: 2026-10-16
scope: [src/paddock/config/context.py, src/paddock/config/extract.py, src/paddock/config/filters.py, src/paddock/config/schema.py, src/paddock/config/sources/, docs/usage/]
summary: Validate every [projects] entry's shape on each run, keys included, but check host paths on disk only in the entry that applies to this run; not every entry's paths, and not skipping other entries' validation altogether.
revisit-when: More than one [projects] entry can apply to a run, or an entry applies other than by its key equalling the resolved workdir, such as parent-directory inheritance; paddock gains an operation that acts on every project's entry.
---

# 013: Check Host Paths Only in the Matching Projects Entry

## Context

The user source validates the whole user file on every run, every `[projects]` entry
included, and validation checks each host path (`build.context`, `build.dockerfile`,
`volumes` keys) on disk. So an entry whose project has been moved, deleted or unmounted
stops paddock in every project, though it can only ever apply to its own. A key that
isn't a real directory, such as a typo or `~/code/widgets`, does the same once its entry
holds a relative path, since [ADR 012][] resolves those against the key.

That ADR left this coupling to its revisit trigger "a stale `[projects]` entry for
another project stops runs in practice". This ADR answers it.

The matching entry is validated twice: by the user source, as one of the file's
entries, and by the `project_overrides` source, which applies it. A bad path in it is
reported under both labels.

## Options

### Option 1: Do nothing

**Pros:** A mistake anywhere in the user file surfaces on the next run, wherever it is.
**Cons:** The state of one project's directory decides whether every other project can
run. The fix is to edit a file in a project the user isn't working in, often for a
project they have finished with.
**Risks:** Users delete `[projects]` entries they still want, or stop using them, to
keep paddock running.

### Option 2: Check shape everywhere, host paths only in the matching entry (Accepted)

The user source validates every entry for shape: known keys, value types, agent
values, build policies, container paths and allowlist entries. Each key must be a
normalised absolute path, the only form that can equal a resolved workdir. Host paths
are left as written, touching nothing on disk. `project_overrides` validates the
matching entry in full, host paths included, against the workdir.

**Pros:** What is checked everywhere is what the user wrote, which doesn't change
behind their back; what depends on disk is checked only where it applies. A bad path in
the matching entry is reported once; a shape error in it is still reported by both
sources.
**Cons:** Shape and path checks need separate modes, which the schema must carry.
**Risks:** A host path in another project's entry that was wrong when written surfaces
only when that project runs. An entry keyed by a symlinked or since-moved path is
well-formed but never applies, silently.

### Option 3: Validate only the matching entry

Parse the file, then validate only the entry `project_overrides` applies.

**Pros:** Simplest schema: other entries are opaque.
**Cons:** A misspelt key or wrong type in another project's entry surfaces only when
that project runs, long after the edit that caused it, so a user editing their file
from one project gets no feedback on the rest.
**Risks:** A typo in a rarely run project's allowlist goes unnoticed until it matters.

### Option 4: Warn about other entries' missing paths

Check every entry's host paths, but report a failure outside the matching entry as a
warning rather than an error.

**Pros:** Flags a stale entry without blocking work.
**Cons:** The warning repeats on every run in every project until the entry is fixed,
which trains users to ignore paddock's warnings.
**Risks:** A warning that matters is lost among stale-entry ones.

## Decision

Option 2. Shape errors are the user's own edits, so reporting them at once, from any
project, is feedback; a missing path is the state of a directory the run doesn't use,
so reporting it there is coupling. Option 3 discards the first to remove the second,
and Option 4 keeps the second as noise.

## Consequences

- Moving or deleting a project no longer affects other projects' runs.
- A `[projects]` key that can never match a workdir (`~/code/widgets`, a relative
  path, a trailing slash) now stops every run with an error naming it, where before
  it was ignored unless it held a relative path.
- A bad host path in the matching entry is reported once, as
  `project_overrides:<key>`, rather than also as `user:projects.<path>.<key>`. Path
  errors now name the path checked as well as the value as written.
- Shape-only output keeps host paths relative, so it must never reach the merge; the
  user source strips `[projects]` before it does. A new host-path directive must go
  through the same switch as the existing ones, or it touches disk for every entry.
- Other entries' host paths are never resolved, so ADR 012's rule that an entry
  resolves against its own key now only matters for the matching entry, whose key is
  the workdir.

[ADR 012]: 012-resolve-relative-config-paths-against-the-workdir.md
