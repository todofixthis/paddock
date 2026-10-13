---
status: Accepted
date: 2026-10-13
scope: [src/paddock/config/filters.py, src/paddock/config/schema.py, src/paddock/config/sources/, docs/usage/]
summary: Resolve a relative host path in config against the directory its source belongs to (the workdir for .paddock/config.toml and [projects] entries, the user config file's directory for the rest of that file, the cwd for env and CLI), not against the process cwd for every source.
revisit-when: Users need a path in the user file's global section to resolve per project, such as one cache mount declared once for every workdir.
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

Environment variables and flags have no file; the user typed them in a shell, whose cwd
is the only directory they could mean.

## Options

### Option 1: Do nothing

**Pros:** No change; one rule for every source.
**Cons:** A relative path in a file is only correct from one cwd, so in practice every
file path must be absolute or `~`-relative, and a project can't mount anything relative
to itself.
**Risks:** A path that happens to exist under the wrong cwd validates and mounts the
wrong directory silently.

### Option 2: Resolve against the directory the source belongs to (Accepted)

Project-scoped sources — `.paddock/config.toml` and a `[projects."<workdir>"]` entry —
resolve against the workdir. The rest of the user file resolves against that file's
directory. Env and CLI keep the cwd. `~` still expands first, and absolute paths are
unaffected. Each source passes its base directory into the schema; `Filepath` joins a
relative path onto it before resolving.

**Pros:** A path means the same thing from any cwd; `"data"` and `"../sibling"` work in
a committed project file and in a per-project entry.
**Cons:** Four sources, three bases: a path copied from the CLI into a file can change
meaning. A `[projects]` entry, though written in the user file, resolves against the
project, not the file.
**Risks:** A new source that forgets to pass a base gets the cwd, the old behaviour,
rather than an error.

### Option 3: Resolve against each file's own directory

Every TOML source resolves against the directory holding the file: `.paddock/` for the
project file, the user config directory for the whole user file, `[projects]` entries
included.

**Pros:** One rule for every file, the one most config formats use.
**Cons:** The project file lives one level below the project, so the project root is
`..` and a sibling is `../../sibling`. A `[projects]` entry resolving against
`~/.config/paddock/` can't name anything in its own project without an absolute path —
the case the entry exists for.
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
shell they were typed in. Option 3 gets the user file's global section right but puts a
project's paths one level off and strands `[projects]` entries. Option 4 makes the
gotcha an error without delivering what users wanted from relative paths.

The user file's base is the parent of the path paddock read it from, not following
symlinks, so a user file symlinked from a dotfiles repository resolves against
`~/.config/paddock/`, where its users look for it.

`[projects]` entries for other projects are also validated whenever the user file
loads; each resolves against its own key, so a relative path in one is checked against
the project it names, not the one being run.

## Consequences

- `.paddock/config.toml` can mount `../sibling` and build from `images/Dockerfile`
  inside the project, and so can a `[projects]` entry. A path in the project file can
  now reach outside the project relative to it; it could already do so absolutely, and
  the `project_toml` allowlist still gates it.
- A user file relying on the old behaviour — a relative path that only worked from one
  cwd — now resolves elsewhere. Such a file was broken from any other cwd, so this is
  a fix, but it is a behaviour change worth a release note.
- Resolved paths are absolute, so the merged-config pass that re-runs the schema is
  unaffected by which base it uses.
- A new config source must pass the base its paths belong to; leaving it out silently
  falls back to the cwd.

[`docs/usage/configuration.md`]: ../usage/configuration.md
[`Filepath`]: ../../src/paddock/config/filters.py
