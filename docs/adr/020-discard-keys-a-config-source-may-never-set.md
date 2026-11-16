---
status: Accepted
date: 2026-11-16
scope: [docs/usage/, src/paddock/config/loader.py, src/paddock/config/sources/]
summary: A config source removes any key it may never set before validation and reports it with a reason, as a warning when that source is enabled, so the key is ignored without stopping the run (not a validation error, and not the allowlist's dropped-keys warning, whose remedy does not apply); the project file's config, projects and agents.<name>.server are such keys; a key that is merely unknown, or sits in the user's own file or shell, stays a validation error.
revisit-when: A second source of committed or otherwise untrusted config appears; users report believing a discarded key applied because they missed the warning; a run needs discards to be fatal, as a strict or CI mode might; a discarded key gains a meaning the project file may legitimately carry.
---

# 020: Discard Keys a Config Source May Never Set

## Context

The project file (`.paddock/config.toml`) is the one source of committed config, and
some keys are never its to set: `config` and `projects` belong to the user's own file,
and `agents.<name>.server` describes a server shared by every project ([ADR 019][]).

An enabled source is validated whole before the allowlist filters it ([ADR 004][]).
So a key the project file may never set, written as it is today for `config` and
`projects`, is an unexpected key, and stops the run of everyone who granted that file
anything at all:

```
[project_toml:config] Unexpected key "config".
```

ADR 019 decided that server settings in the project file are removed before
validation instead, with a warning. That left two rules for one situation.

It matters more once a server can mount many projects read-write: an agent working in
one can then write another's project file, so stopping a run takes no commit.

The allowlist already reports keys it drops, with a remedy: "add them to
[config.allowlist] to keep them". No grant can keep these keys.

## Options

### Option 1: Do nothing

`config` and `projects` in the project file stay validation errors; only server
settings are discarded.

**Pros:** The loudest response to a file trying to grant itself access.
**Cons:** Two rules for keys of one kind. The loud response is also a way to stop
every opted-in user's runs.
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
**Cons:** Still two rules, and still a way to stop runs, now by the key most likely
to be written by something hostile.
**Risks:** As Option 1.

## Decision

Option 2. A key the project file may never set is ignored under every option; what
differs is whether writing it stops the run. Stopping serves nobody the file's author
is not already able to inconvenience, and under a shared server that author may be an
agent.

- **What counts.** A key that is valid config somewhere, and that this source may
  never set whatever the allowlist grants. For the project file: `config`,
  `projects` and each `agents.<name>.server`. A key that is merely unknown, such as
  a misspelt `confg`, stays a validation error.
- **Only untrusted content.** The user's own file and shell keep their errors: server
  settings in a `[projects]` entry, or an unknown `PADDOCK_*` variable, are the
  user's own typos, and a stop is how they are found.
- **Before validation.** The key's contents are never validated, so nothing under it
  can stop the run.
- **Reported with the source's reason,** as `<source>: ignored <path> — <reason>`,
  where that source is enabled. A disabled source is ignored whole and draws nothing
  more than it does today. The reason comes from the source, so the loader needs no
  change for a new kind of discard.

## Consequences

- A project file can no longer stop a run by holding `config` or `projects`. The
  docs' troubleshooting entry for that error becomes one for the warning.
- A project file that tries to set its own allowlist now draws a warning the user
  can miss, where it drew a stop. The grant is ignored exactly as before.
- Discards join the allowlist's drops as things a user must read warnings to learn;
  a future check of config, such as the planned `doctor` command, should report
  both.

[ADR 004]: 004-gate-untrusted-config-sources-with-an-allowlist.md
[ADR 019]: 019-run-one-shared-container-per-agent-server.md
