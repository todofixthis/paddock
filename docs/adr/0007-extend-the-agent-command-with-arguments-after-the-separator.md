---
status: Accepted
date: 2026-09-26
scope: [README.rst, docs/usage/, src/paddock/__main__.py, src/paddock/cli.py, src/paddock/docker/builder.py]
summary: Append arguments after -- to the agent's own command (paddock -- --continue runs claude --continue); only a bare positional replaces the command.
revisit-when: An agent's command needs user arguments placed anywhere but its end.
---

# 0007: Extend the Agent Command with Arguments After the Separator

## Context

paddock's CLI ends its own flags at the first positional or at `--`, and until now both
replaced the agent's command outright. `paddock --agent=claude -- --continue` therefore ran
`--continue` as the container command, rather than `claude --continue`. The usual reason to
reach for `--` is to pass flags to the agent, but to do that the user had to restate the
agent's command: `paddock -- claude --continue`. That repetition also ties the invocation
to one agent.

## Options

### Option 1: Do nothing

**Pros:** Keeps one rule for both stop-points. Existing `paddock -- claude …` invocations
keep working.
**Cons:** Passing flags to the agent requires restating its command.
**Risks:** A user who writes `paddock -- --continue` gets an unfindable-command error from
Docker, or a hang where the image's `ENTRYPOINT` treats `--continue` as its own argument.

### Option 2: `--` extends the agent command; a positional replaces it (Accepted)

**Pros:** Each stop-point has one job, and the user's choice of stop-point says which
behaviour they want.
**Cons:** Changes existing behaviour. `paddock -- claude --continue` now runs
`claude claude --continue`.
**Risks:** A replacement command whose first token starts with `-` can no longer be given
at all, because a positional cannot start with `-`.

### Option 3: Both stop-points extend the agent command

**Pros:** One rule, and no way to confuse the two stop-points.
**Cons:** Removes the only way to run a different program in the container, such as
`paddock bash`. That takes away a debugging route that `--agent=false` covers only for
bash.

## Decision

Option 2. Flags for the agent are the common case, and `--` is the conventional way to
pass them through. A positional is a program name by construction, so it still replaces
the command. The risk under Option 2 accepts the loss of a case nobody has asked for.

## Consequences

- `ParsedArgs` carries the arguments after `--` separately from a replacement command.
  When a replacement command is given, the builder uses it as-is. Otherwise the builder
  appends the `--` arguments to `get_command()`.
- Anyone scripting `paddock -- <program> …` must drop the `--`.
- The README and the usage docs change to match.
