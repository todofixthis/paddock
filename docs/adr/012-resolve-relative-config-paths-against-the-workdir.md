---
status: Accepted
date: 2026-10-13
scope: [src/paddock/__main__.py, src/paddock/config/filters.py, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/config/sources/, docs/usage/]
summary: Resolve a relative host path in config against the workdir, whichever source sets it (each [projects] entry against its own key, the workdir it applies to), passed explicitly by every source; not against the process cwd, and not against a different base per source.
revisit-when: Global relative paths prove unworkable because they are missing in some projects, such as users asking for mounts skipped when absent; users need env or CLI paths to follow the shell's cwd when it differs from the workdir; project config discovery lets the project file's directory diverge from the workdir.
revisit-discharged-by: [13]
---

# 012: Resolve Relative Config Paths Against the Workdir

## Context

Three directives take host paths: `build.context`, `build.dockerfile` and the host side
of `volumes`. Every source validates them through the same [`Filepath`][] filter, which
calls `Path.resolve()` and so resolves a relative path against the process cwd, whatever
source it came from.

That makes a relative path in a file mean something different depending on where
paddock is run. `.paddock/config.toml` holding `[volumes] "data" = "/data"` works from the
project root and fails under `--workdir=<project>` from anywhere else.
[`docs/usage/configuration.md`][] documents this as a gotcha and tells users to write
absolute or `~`-relative paths, which leaves a committed project file no way to name a
path inside or beside the project — `../sibling` for a sibling repository, say — that
holds on every developer's machine.

paddock merges five sources by precedence. What keeps that tractable is that a
directive's value means the same thing whichever source sets it. The user file holds
global configuration, so it can't simply be treated like a project-level file, even
though both are TOML.

Drafted as ADR 011 and renumbered to 012 when an ADR merged first under that number.

## Options

### Option 1: Do nothing

**Pros:** No change; one rule for every source.
**Cons:** A relative path in a file is only correct from one cwd, so in practice every
file path must be absolute or `~`-relative, and a project can't mount anything relative
to itself.
**Risks:** A path that happens to exist under the wrong cwd validates and mounts the
wrong directory silently.

### Option 2: Resolve against the workdir, from every source (Accepted)

Every source resolves a relative path against the workdir: `.paddock/config.toml`, the
user file, env and CLI alike. A `[projects."<path>"]` entry resolves against its own
`<path>`, which is the workdir it applies to. `~` still expands first, and absolute paths
are unaffected. Every source passes its base into the schema, which requires one;
`Filepath` joins a relative path onto it, then resolves the result.

**Pros:** A value means the same thing in every source, so moving it between sources,
or overriding it in a higher one, never changes what it names. `"data"` and
`"../sibling"` work in a committed project file and anywhere else.
**Cons:** The user file's global section can't name a path beside the user file
relatively; it needs `~`. A global relative path names a different directory in each
project, so one that doesn't exist in some project stops every run there. Under
`--workdir`, a relative `--volume` or `PADDOCK_BUILD_DOCKERFILE` no longer means what the
shell's tab completion suggested.
**Risks:** Under `--workdir`, a relative path that worked because it existed under the
cwd now resolves under the workdir; if a same-named path exists there, it mounts
silently.

### Option 3: Resolve against the directory each source belongs to

`.paddock/config.toml` and `[projects]` entries resolve against the project, the rest of
the user file against its own directory, and env and CLI against the cwd.

**Pros:** Each base is the one its source is arguably about, and shell-typed paths keep
the shell's meaning.
**Cons:** Five sources, three bases: the same value names different paths depending on
which source sets it, so copying a line between sources, or overriding one, can change
what it names. That undoes what keeps precedence tractable.
**Risks:** Users reason about a merged config by value and get the wrong path.

### Option 4: Reject relative paths in files

Fail validation on any relative host path from a TOML source.

**Pros:** No ambiguity, and an error rather than a wrong mount.
**Cons:** Removes the project-relative mounts this change is for, and with them any
portable way for a committed file to name a path:

- **Portability:** an absolute path names one machine's layout (`/home/alice/code/…`),
  so a project file holding one breaks for every other developer, in CI, and on a
  different OS. A `~`-relative path only moves the problem: every developer must clone
  the project to the same place under their home.
- **Coupling to the checkout's location:** a project that builds its own image must
  point `build.dockerfile` and `build.context` at files inside its own repository by
  absolute or `~` path. The paddock config then breaks whenever the checkout is moved
  or renamed, though the Docker build itself hasn't changed, and a second clone
  silently builds from the first clone's files.

**Risks:** Developers work around it with per-machine copies of the project file or
`[projects]` entries, so the committed file stops describing the project.

## Decision

Option 2. Every run has exactly one workdir, and every source configures that run, so
the workdir is the one base all five share. Keeping a value's meaning independent of
its source matters more than giving each source its most natural base, which is
Option 3's whole advantage. The workdir defaults to the cwd, so the shell-typed case
Option 3 protects only differs under `--workdir`. Option 4 turns the gotcha into an
error without delivering the relative paths users wanted.

The base is a required argument of the schema, with no fallback: every source and the
merged-config pass name it explicitly. A new source that runs paths through the schema
without a base fails at once, as ADR 004 makes a source that forgets its allowlist
default fail closed. `Filepath` and `VolumeMap` on their own still default to the cwd,
so a source that pre-validates paths with either, as env does, passes its base there
too.

Concrete semantics:

- **The workdir** is the resolved workdir, so `../sibling` from a symlinked checkout is
  a sibling of the real directory, matching the `[projects]` key lookup.
- ~~**Every `[projects]` entry** is validated whenever the user file loads, each against
  its own key: the workdir it would apply to, and the current workdir for the entry
  that matches. A key that isn't absolute (`~` in a key isn't expanded) never matches a
  workdir, and its relative paths resolve against the key taken relative to the cwd
  (a `~` key as a directory literally named `~`), so they usually fail validation.~~
  Since ADR 013, only the entry that applies to the run has its host paths checked,
  against its key, which is the workdir; a key that can never match is a shape error.

## Consequences

- `.paddock/config.toml` can mount `../sibling` and build from `images/Dockerfile`
  inside the project, and so can every other source. Relative paths are not confined
  to the project: a `volumes` grant to `project_toml` still reaches the whole host
  filesystem, as absolute paths always could.
- Without `--workdir` the workdir is the cwd, so relative paths in the project file,
  the user file's global section, the matching `[projects]` entry, env and CLI resolve
  as they did before. Under `--workdir` from another
  directory they all now resolve against the workdir, not the shell. The release notes
  must call this out.
- ~~Relative paths in other projects' `[projects]` entries resolve against their own key
  rather than the cwd, so they stop failing in projects that happen not to hold them.
  Such an entry still fails validation — and stops paddock in every project — once its
  own project is moved, deleted or unmounted, as absolute paths in other projects'
  entries always did. Checking paths only in the entry that matches the workdir would
  remove that coupling; it predates this decision and is left to the revisit trigger.~~
  Spent by ADR 013, which checks paths only in the matching entry.
- ~~A path that fails validation is reported by its raw value (`Path 'data' does not
  exist`), not the path paddock checked, so a user must know the workdir rule to see
  where it looked.~~ The error now names the path paddock checked as well (ADR 013).
- Resolved paths are absolute, so the merged-config pass that re-runs the schema is
  unaffected by its base.
- A change to how the workdir is resolved in [`__main__.py`][] changes what every
  relative path means.

[`__main__.py`]: ../../src/paddock/__main__.py
[`docs/usage/configuration.md`]: ../usage/configuration.md
[`Filepath`]: ../../src/paddock/config/filters.py
