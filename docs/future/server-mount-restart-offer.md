# Offer to Restart a Server with a New Mount

A server that runs tools in the project (OpenCode) must have the workdir mounted.
Paddock stops when it is not, naming the mounted roots and the command that recreates
the server. Docker cannot add a mount to a running container.

## Suggested change

When the workdir lies outside the server's mounts, offer to add it and restart the
server, instead of only stopping.

## Open questions

- Restarting ends live sessions in other projects. Refuse while clients are connected,
  or ask?
- Where the new mount is recorded. Server settings are read only from the user
  config's global section, so a mount added for one run either edits that file or
  lasts only until the next restart.
- What non-interactive runs do.

## Why deferred

Out of scope for the first agent-server mahi
(`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`). It fits
`paddock service` (`cli-subcommands.md`).
