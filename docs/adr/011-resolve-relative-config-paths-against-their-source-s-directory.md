---
status: Accepted
date: 2026-10-13
scope: [src/paddock/__main__.py, src/paddock/config/filters.py, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/config/sources/, docs/usage/]
summary: Resolve a relative host path in config against the directory its source belongs to (the workdir for .paddock/config.toml, each [projects] entry's own key, the user config file's unresolved parent for the rest of that file, the cwd for env and CLI), passed explicitly by every source, not against the process cwd by default.
revisit-when: Users need a path in the user file's global section to resolve per project, such as one cache mount declared once for every workdir; a config source is added whose paths belong to no single directory; project config discovery lets the project file's directory diverge from the workdir.
---

# 011: Resolve Relative Config Paths Against Their Source's Directory

## Context

Three directives take host paths: `build.context`, `build.dockerfile` and the host side
of `volumes`. Every source validates them through the same [`Filepath`][] filter, which
calls `Path.resolve()` and so resolves a relative path against the process cwd, whatever
source it came from.

That makes a relative path in a file mean something different depending on where
paddock is run. `.paddock/config.toml` holding `[volumes] "data" = "/data"` works from the
project root and fails under `--workdir=<project>` from anywhere else; a user-file
`build.dockerfile = "images/Dockerfile"` works only from the user config directory.
[`docs/usage/configuration.md`][] documents this as a gotcha and tells users to write
absolute or `~`-relative paths, which leaves a committed project file no way to name a
path inside or beside the project — `../sibling` for a sibling repository, say — that
holds on every developer's machine.

## Options

### Option 1: Do nothing

**Pros:** No change; one rule for every source.
**Cons:** A relative path in a file is only correct from one cwd, so in practice every
file path must be absolute or `~`-relative, and a project can't mount anything relative
to itself.
**Risks:** A path that happens to exist under the wrong cwd validates and mounts the
wrong directory silently.

### Option 2: Resolve against the directory the source belongs to (Accepted)

`.paddock/config.toml` resolves against the workdir. Each `[projects."<path>"]` entry
resolves against its own `<path>`. The rest of the user file resolves against the
directory paddock read it from. Env and CLI keep the cwd. `~` still expands first, and
absolute paths are unaffected. Every source passes its base into the schema, which
requires one; `Filepath` joins a relative path onto it, then resolves the result.

**Pros:** A path means the same thing from any cwd; `"data"` and `"../sibling"` work in
a committed project file and in a per-project entry.
**Cons:** Five sources, four bases: a path copied from the CLI into a file can change
meaning. A `[projects]` entry, though written in the user file, resolves against its
project, not the file. Env vars loaded from a file (direnv's `.envrc`, a CI config)
still resolve against the cwd, so they break from a subdirectory.
**Risks:** A relative path in the user file's global section that worked because
paddock was always run from the project root now resolves under the config directory;
if a same-named path exists there, it mounts silently.

### Option 3: Resolve against each file's own directory

Every TOML source resolves against the directory holding the file: `.paddock/` for the
project file, the user config directory for the whole user file, `[projects]` entries
included.

**Pros:** One rule for every file, the one most config formats use.
**Cons:** The project file lives one level below the project, so the project root is
`..` and a sibling is `../../sibling`. A line moved between `.paddock/config.toml` and
the matching `[projects]` entry changes meaning.
**Risks:** None beyond the cons.

### Option 4: Reject relative paths in files

Fail validation on any relative host path from a TOML source.

**Pros:** No ambiguity, and an error rather than a wrong mount.
**Cons:** Removes the project-relative mounts this change is for.
**Risks:** None beyond the cons.

## Decision

Option 2. The base a path needs is the directory the source is *about*: a project file
or project entry describes the project, so its paths are project paths; the user file's
global section describes the user's setup and lives beside it; env and CLI describe the
shell they were typed in, whose cwd is the only directory they can name. Anchoring a
`[projects]` entry to its project means a line moves between `.paddock/config.toml` and
the entry without changing meaning, which Option 3 breaks. Option 4 turns the gotcha
into an error without delivering the relative paths users wanted.

The base is a required argument of the schema, with no fallback: env, CLI and the
merged-config pass name `Path.cwd()` explicitly. A new source that runs paths through
the schema without a base fails at once, as ADR 004 makes a source that forgets its
allowlist default fail closed. `Filepath` and `VolumeMap` on their own still default
to the cwd, so a source that pre-validates paths with either, as env does, passes its
base there too.

Concrete semantics:

- **The workdir** is the resolved workdir, so `../sibling` from a symlinked checkout is
  a sibling of the real directory, matching the `[projects]` key lookup.
- **The user file's base** is the parent of the path paddock read it from, without
  following a symlink to the file itself. The joined path is then resolved, so symlinked
  directories along it are followed: with `~/.config/paddock` itself a symlink, paths
  land beside its target. A dotfiles user who links only the file and keeps an
  `images/` beside it in the repository has to link that too; we take that over a base
  that moves when the file is relinked.
- **Every `[projects]` entry** is validated whenever the user file loads, each against
  its own key. A key that isn't absolute (`~` in a key isn't expanded) never matches a
  workdir, and its relative paths resolve against the key taken relative to the cwd
  (a `~` key as a directory literally named `~`), so they usually fail validation.

## Consequences

- `.paddock/config.toml` can mount `../sibling` and build from `images/Dockerfile`
  inside the project, and so can a `[projects]` entry. Relative paths are not confined
  to the project: a `volumes` grant to `project_toml` still reaches the whole host
  filesystem, as absolute paths always could.
- A user file with a relative path in its global section changes meaning: it worked
  whenever paddock ran from the one directory holding that path, and now resolves under
  the config directory. The release notes must call this out.
- A `[projects]` entry with relative paths fails validation — and stops paddock in
  every project — once its project is moved, deleted or unmounted. Absolute paths in
  other projects' entries already did this; relative ones make it likelier, since they
  almost always point inside their own project.
- Resolved paths are absolute, so the merged-config pass that re-runs the schema is
  unaffected by its base.
- A change to how the workdir is resolved in [`__main__.py`][] changes what every
  project-relative path means.

[`__main__.py`]: ../../src/paddock/__main__.py
[`docs/usage/configuration.md`]: ../usage/configuration.md
[`Filepath`]: ../../src/paddock/config/filters.py
