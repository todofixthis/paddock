# Warnings the User Can Suppress One by One

Paddock's warnings are log lines. `--quiet` hides all of them or none, and a warning
shown on every run is soon read past. So a risk a user has knowingly accepted, such as
sharing OpenCode's data directory with the host (ADR 021), can only be documented: a
warning for it would nag those who chose it, and silence would hide it from those who
did not understand the choice.

## Suggested change

Give each warning a stable identifier and print it with the warning. A user silences
one by naming it in config, and only that one. A risk can then be put in front of the
user on every run until they say they have read it.

## Open questions

- Where the list lives, and whether a project file may add to it. A project file that
  could silence the warning about its own grant would defeat the warning.
- Whether a suppression is global, per project, or either.
- Whether it binds to the kind of warning or to the particular thing accepted: this
  host path at this container path. Silencing the kind would also silence a later,
  different mount the user never weighed.
- Whether `--quiet` still hides a warning nobody has suppressed.
- Which warnings may never be suppressed.
- Whether identifiers are stable across releases, and what happens to a suppression
  whose warning is gone.
- Whether a suppressed warning is still counted or shown by `paddock doctor`
  (`cli-subcommands.md`).

## Why deferred

It changes how every warning is emitted, which is wider than the agent-server mahi
that raised it (`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`).
First candidates once it exists: server drift, which warns today, and two warnings
that do not exist yet, for a host directory mounted over a server's own volume and for
`project_toml` granted under a server's read-write mounts (ADR 019).
