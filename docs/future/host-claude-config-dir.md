# Honour a Host `CLAUDE_CONFIG_DIR`

Claude Code keeps its settings and sign-in in `~/.claude`, and its onboarding state in
`~/.claude.json` beside it, unless `CLAUDE_CONFIG_DIR` names another directory, in which
case both live there. The `claude` agent always mounts the host's
`~/.claude` and `~/.claude.json`, whatever that variable says. A user who sets `CLAUDE_CONFIG_DIR`
on the host gets a container that mounts an empty or stale `~/.claude` and starts at
onboarding, with nothing saying why.

## Suggested change

Read `CLAUDE_CONFIG_DIR` from the environment paddock runs in. When it is set, mount
that directory in place of `~/.claude` and `~/.claude.json`, and set the variable in the
container to wherever it is mounted.

## Open questions

- Whether the directory mounts at its host path or at `/root/.claude`. Claude Code
  records paths in its state, so the two may not be interchangeable.
- What to do when the variable names a directory that does not exist.
- Whether a relative value is resolved against the directory paddock ran in or
  rejected.
- Whether this is the `claude` agent's alone. The planned Omnigent client, which runs
  Claude Code through another tool, is to keep Claude's config in a volume of paddock's
  own, apart from the host's (see the design doc below), and would then ignore the
  host's variable by design.
- Whether `config.allowlist` has a say: an environment variable would then change what
  paddock mounts.

## Why deferred

Raised while deciding where the planned Omnigent client keeps Claude's config
(`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`, "Omnigent"). It is a fault in
the `claude` agent as it stands, apart from that work.
