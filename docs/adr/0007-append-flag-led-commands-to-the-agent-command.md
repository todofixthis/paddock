---
status: Accepted
date: 2026-09-26
scope: [.agents/skills/, README.rst, docs/usage/, images/, src/paddock/__main__.py, src/paddock/agents/, src/paddock/cli.py, src/paddock/docker/builder.py]
summary: Append a container command that starts with a flag to the agent's command (paddock -- --continue runs claude --continue), and let any other command replace it; not a separate agent-args channel or flag.
revisit-when: Users need to pass the agent a prompt or subcommand without repeating its command; an image's ENTRYPOINT needs flags without the agent's command in front of them; an agent's command needs user arguments anywhere but its end.
---

# 0007: Append Flag-Led Commands to the Agent Command

## Context

paddock's own flags end at the first positional or at `--`. Everything after that point
is the container command, and it used to replace the agent's command outright. So
`paddock --agent=claude -- --continue` ran `--continue` in the container, not
`claude --continue`. The main reason to reach for `--` is passing flags to the agent, and
to do that the user had to name the agent again: `paddock -- claude --continue`. The
README's own example, `paddock --image=my-claude-image -- --allow-dangerously-skip-permissions
--continue`, was broken for this reason. The README builds `my-claude-image` from
`images/Dockerfile`, which sets no `ENTRYPOINT`, so Docker tried to run the flag as a program.

Replacing the command is still needed. `paddock --agent=claude -- /bin/bash` opens a shell
in a container that `ClaudeAgent` set up, with its mounts and container name, which makes
it the way to debug an agent's environment.

paddock is pre-release, so the CLI can change without a deprecation period.

## Options

### Option 1: Do nothing

**Pros:** One rule, with no special cases.
**Cons:** Passing flags to the agent means naming the agent again.
**Risks:** `paddock -- --continue` gives an error that doesn't point at the cause. With an
image that has no `ENTRYPOINT`, Docker reports that it can't find `--continue`.

### Option 2: Choose by the first token (Accepted)

If the container command starts with a flag, append it to the agent's command. Otherwise
it replaces the agent's command. Only `--` can bring in a flag-led command, because a
positional can't start with `-`.

**Cons:** Arguments that don't start with a flag, such as a prompt or subcommand, still
need the agent's command repeated: `paddock -- claude mcp list`. A replacement program whose
name starts with `-` has to be given as a path (`./-x`).
**Risks:** With an image whose `ENTRYPOINT` is the agent itself, `paddock -- --foo` used to
send the entrypoint `--foo`. It now sends `claude --foo`, and `claude claude --foo` reads the
extra `claude` as a prompt without raising any error. paddock's own image and the
entrypoint recommended in the usage docs aren't affected. Any agent command that can't take
extra arguments on the end silently drops them; `['sh', '-c', 'claude']`, for example,
turns them into `$0` and `$1`.

### Option 3: `--` always appends; a positional always replaces

**Pros:** The user decides which by the separator they choose, with no guessing from the
first token. A prompt or subcommand needs no repeated agent command: `paddock -- mcp list`
runs `claude mcp list`.
**Cons:** `--agent=claude -- /bin/bash` would run `claude /bin/bash`, and existing
`paddock -- claude …` commands would silently run `claude claude …`.

### Option 4: A separate flag for agent arguments

For example, `--agent-args='--continue'`.

**Cons:** It adds a flag that is quoted as a single string, so paddock has to split it the
way a shell would. It also leaves `--`, the conventional way to pass arguments through,
doing the less common job.

## Decision

Option 2. Flags are what users pass to an agent most often, and a command that starts with
a flag is almost never a program to run. So the first token settles the common case without
ambiguity. Option 2 beats Option 3 on compatibility: every command that worked before still
works, and `--` can still replace the command. Only flag-led commands change, and they did
something useful only with an image whose `ENTRYPOINT` is the agent. The price is the
prompt and subcommand cases, which Option 3 would have avoided, and it's accepted.

## Consequences

- The builder decides whether to append or replace. The parser still produces a single
  command.
- Every agent's `get_command()` must accept extra arguments on the end. The `BaseAgent`
  docstring says so.
- The README, the usage docs and `--help` describe the rule.
