---
status: Accepted
date: 2026-11-16
scope: [docs/usage/, src/paddock/config/loader.py, src/paddock/config/schema.py, src/paddock/config/sources/]
summary: A source of committed config removes any key that is valid config elsewhere but never that source's to set, before validation and whatever its value, and reports it with a reason, as a warning when that source is enabled, so the key is ignored without stopping the run (not a validation error, and not the allowlist's dropped-keys warning, whose remedy does not apply); the project file's config, projects and agents.<name>.server are such keys; a key that is merely unknown stays a validation error, and the user's own file, the environment and the command line discard nothing, keeping their validation errors.
revisit-when: An enabled project file's validation errors stop being fatal; users report believing a discarded key applied because they missed the warning; a run needs discards to be fatal, as a strict or CI mode might; the environment or command line comes to be treated as untrusted by default; discards need reporting for a disabled source; a discarded key gains a meaning the project file may legitimately carry.
---

# 020: Discard Keys a Config Source May Never Set

## Context

The project file (`.paddock/config.toml`) is the one source of committed config, and
some keys are never its to set: `config` and `projects` belong to the user's own file,
and `agents.<name>.server` describes a server shared by every project ([ADR 019][]).

Every enabled source is validated whole, and only then filtered by the allowlist
([ADR 003][]). Before this decision, `config` or `projects` in the project file was
therefore an unexpected key, which stopped the run of everyone who had granted that
file anything at all:

```
[project_toml:config] Unexpected key "config".
```

ADR 019 decided that server settings in the project file are removed before
validation instead, with a warning. That left two rules for one situation.

The allowlist ([ADR 004][]) already reports keys it drops, and the loader's warning
gives a remedy: "add them to [config.allowlist].<source> to keep them". No grant can
keep these keys.

## Options

### Option 1: Do nothing

`config` and `projects` in the project file stay validation errors; only server
settings are discarded.

**Pros:** The loudest response to a file trying to grant itself access.
**Cons:** Two rules for keys of one kind, and a stop for a key that would have been
ignored anyway.
**Risks:** Each later key of this kind needs the choice made again.

### Option 2: The source discards them before validation and says why (Accepted)

A source removes each key it may never set and hands the loader the path and a
reason. The loader warns, once per key, where that source is enabled.

**Pros:** One rule. The key is ignored either way, so the outcome for security is the
same as an error's.
**Cons:** A warning is quieter than a stop, and `--quiet` hides it.
**Risks:** A user who misses the warning believes a committed setting applied.

### Option 3: Report them as allowlist drops

Treat them as keys no rule permits, through the allowlist's existing warning.

**Pros:** No new mechanism.
**Cons:** That warning's remedy is false here, and the allowlist acts after
validation, so a malformed value under such a key would still stop the run.
**Risks:** Users add the key to their allowlist and find nothing changes.

### Option 4: Discard most, but stop on `config`

**Pros:** Keeps the loud response for the one key that reads as an attack.
**Cons:** Still two rules.
**Risks:** As Option 1.

### Option 5: Make every validation error in an enabled project file non-fatal

Warn about whatever in the file does not validate, and apply the rest.

**Pros:** No value in a project file could stop a run, where this decision removes
only three keys from the ways one can.
**Cons:** A file that fails validation is not the file the user granted, and applying
what remains of it runs a container on half a configuration.
**Risks:** A typo in a granted key silently reverts it to a lower source's value.

## Decision

Option 2. A key the project file may never set is ignored under every option; what
differs is whether writing it stops the run, and a stop for a key that is ignored
anyway serves nobody. Option 5 would also let the run go on, but for every error in
the file: it trades a visible stop for a silently partial configuration on keys the
file *is* allowed to set, which is a different and larger decision.

- **What counts.** Both must hold: the key is valid config somewhere, and the source
  is committed content that may never set it, whatever the allowlist grants. Only the
  project file is such a source, the one whose default is to be disabled. Its keys of
  this kind are `config`, `projects` and each `agents.<name>.server`. A key that is
  merely unknown, such as a misspelt `confg`, stays a validation error.
- **Not the user's own input.** The user config, the environment and the command line
  keep their errors, including for names that have no form there, such as
  `PADDOCK_VOLUMES` or server settings in a `[projects]` entry. They are typed by
  whoever starts the run, where a stop is how a typo is found. That holds even where
  a user has gated `env` or `cli`: ADR 004 trusts them by default.
- **Before validation, whatever its value.** The key's contents are never validated,
  so nothing under it can stop the run.
- **Reported with the source's reason,** as `<source>: ignored <path> — <reason>`,
  where that source is enabled. The reason comes from the source, so the loader needs
  no change for a new kind of discard.

## Consequences

- A project file can no longer stop a run by holding `config` or `projects`. It can
  still stop one with broken TOML, or an invalid value under any other key, granted
  or not; this decision does not close that.
- A project file that tries to set its own allowlist now draws a warning the user
  can miss, where it drew a stop. The grant is ignored exactly as before: the
  allowlist is built only from the user config and its `[projects]` entry, and that
  must stay so.
- A disabled project file holding only such keys is now silent. It used to draw the
  "had errors but is disabled" warning, so a user who has not opted in no longer
  learns that the file tried.
- The project file's discard set must keep pace with what only the user config may
  hold. A new top-level section joins by being added to the set of user-only
  sections the sources share, which also decides what the user source strips; a
  user-only key nested in an ordinary section, as `agents.<name>.server` is, needs
  its own discard. Either one missed becomes an unexpected-key stop again.
- Discards join the allowlist's drops as things a user must read warnings to learn;
  a future check of config, such as the planned `doctor` command, should report
  both.

[ADR 003]: 003-load-config-through-a-registry-of-sources.md
[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
