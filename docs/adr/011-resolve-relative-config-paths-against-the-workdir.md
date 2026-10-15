---
status: Accepted
date: 2026-10-13
scope: [src/paddock/__main__.py, src/paddock/config/filters.py, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/config/sources/, docs/usage/]
summary: Resolve a relative host path in config against the workdir, whichever source sets it (each [projects] entry against its own key, the workdir it applies to), passed explicitly by every source; not against the process cwd, and not against a different base per source.
revisit-when: Users need a path in the user file's global section to resolve against the user config directory rather than per project; users need env or CLI paths to follow the shell's cwd when it differs from the workdir; project config discovery lets the project file's directory diverge from the workdir.
---

# 011: Resolve Relative Config Paths Against the Workdir

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
**Cons:** The user file's global section can no longer name a path beside the user file
relatively; it needs `~`. A global relative path names a different directory in each
project, so one that doesn't exist in some project stops every run there. Under
`--workdir`, a relative `--volume` or `PADDOCK_BUILD_DOCKERFILE` no longer means what the
shell's tab completion suggested.
**Risks:** A relative path that worked because it existed under the cwd now resolves
under the workdir; if a same-named path exists there, it mounts silently.

### Option 3: Resolve against the directory each source belongs to

`.paddock/config.toml` and `[projects]` entries resolve against the project, the rest of
the user file against its own directory, and env and CLI against the cwd.

**Pros:** Each base is the one its source is arguably about, and shell-typed paths keep
the shell's meaning.
**Cons:** Five sources, four bases: the same value names different paths depending on
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
- **Every `[projects]` entry** is validated whenever the user file loads, each against
  its own key: the workdir it would apply to, and the current workdir for the entry
  that matches. A key that isn't absolute (`~` in a key isn't expanded) never matches a
  workdir, and its relative paths resolve against the key taken relative to the cwd
  (a `~` key as a directory literally named `~`), so they usually fail validation.

## Consequences

- `.paddock/config.toml` can mount `../sibling` and build from `images/Dockerfile`
  inside the project, and so can every other source. Relative paths are not confined
  to the project: a `volumes` grant to `project_toml` still reaches the whole host
  filesystem, as absolute paths always could.
- A relative path in the user file's global section now names a path in each project.
  It suits a mount every project has, and stops any run in a project that lacks it.
  Anything beside the user file needs a `~` path. The release notes must call this out.
- Under `--workdir` from another directory, relative env and CLI paths resolve against
  the workdir, not the shell. Without `--workdir` nothing changes for them.
- A `[projects]` entry with relative paths fails validation — and stops paddock in
  every project — once its project is moved, deleted or unmounted. Absolute paths in
  other projects' entries already did this; relative ones make it likelier, since they
  almost always point inside their own project.
- Resolved paths are absolute, so the merged-config pass that re-runs the schema is
  unaffected by its base.
- A change to how the workdir is resolved in [`__main__.py`][] changes what every
  relative path means.

[`__main__.py`]: ../../src/paddock/__main__.py
[`docs/usage/configuration.md`]: ../usage/configuration.md
[`Filepath`]: ../../src/paddock/config/filters.py
