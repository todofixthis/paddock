# CLI Subcommands

Give `paddock` named commands. Today a bare word after `paddock` replaces the agent's
command (ADR 007), so there is nowhere to put one.

## Commands

- `paddock run`: today's behaviour. `paddock claude` and `paddock run claude` do the
  same thing.
- `paddock service`: manage server containers (list, stop, restart, logs) without
  starting a client. Replaces the `docker rm -f paddock-server-<key>` line Paddock
  prints today.
- `paddock setup`: a guided wizard that writes the user config.
- `paddock doctor`: check config and the environment, and fix common faults.
  It should flag `project_toml = true` and recommend a narrower grant, above all
  for a project under a tool-running server's mounts, where the agent can write the
  project file (ADR 019).

## Open questions

- A reserved word shadows a replacement command of the same name: `paddock doctor`
  runs the doctor, and `paddock run doctor` runs `doctor` in the container. Adding a
  reserved word later breaks anyone already running that command bare, so settle the
  full list before shipping the first one.
- Whether `service restart` should refuse while clients are connected.

## Why deferred

Raised while designing agent servers
(`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`). Server-management
flags were left out of that mahi so they would not need deprecating here.
