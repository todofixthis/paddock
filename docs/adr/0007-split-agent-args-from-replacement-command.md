---
status: Accepted
date: 2026-09-26
scope: [.agents/skills/e2e-testing/, README.rst, docs/usage/docker-images.md, src/paddock/__main__.py, src/paddock/cli.py, src/paddock/docker/builder.py, tests/docker/test_builder.py, tests/test_cli.py, tests/test_main.py]
summary: Tokens after the first -- are appended to the agent's command and never replace it; a positional before -- replaces the command, keeps any later -- verbatim, and is never appended to.
revisit-when: An agent needs its args inserted into its command rather than appended, such as a subcommand before the prompt.
---

# 0007: Split Agent Args from the Replacement Command

## Context

`paddock` took two ways to name what runs in the container — tokens after `--`, or a
positional argument before it — and treated them alike: either replaced the agent's
command. Passing a prompt or flag to the agent meant repeating the agent's own command
(`paddock -- claude --resume`), which ties the invocation to the command an agent class
happens to return, and leaves no way to say "the agent, with these arguments" without it.

The intended grammar, as specified by the maintainer:

- `paddock --agent=claude -- "fix this bug"` runs `claude "fix this bug"`;
  `-- --resume` runs `claude --resume`; `-- /bin/bash` runs `claude /bin/bash`.
- `paddock --agent=claude /bin/bash` runs `/bin/bash` in a container configured for the
  agent; `paddock --agent=claude "fix this bug"` tries to execute `fix this bug`.
- `paddock --agent=claude --resume` fails: paddock has no `--resume` flag.

Two things follow from "before `--` must be a paddock flag". An agent flag spelled exactly
like a paddock one (`--agent`, `--version`) is taken by paddock. An abbreviation of a
paddock flag (`--dry`) is not a paddock flag, so it fails too.

That leaves one case unspecified: a `--` appearing after a replacement command, as in
`paddock web -- --port=4096`.

## Options

### Option 1: Do nothing

**Pros:** No change for anyone relying on `-- <command>`.
**Cons:** No way to pass arguments to the agent without restating its command.
**Risks:** Invocations written as `-- claude …` break silently if an agent's command changes.

### Option 2: `--` appends; a positional replaces and owns everything after it (Accepted)

The first `--` reached while parsing paddock flags ends them, and the tokens after it are
appended to the agent's command. A positional ends them too, and it and every token after
it — a later `--` included — form the replacement command.

**Cons:** A replacement command cannot take separate agent args; there are none to take,
since the agent's command is gone.

### Option 3: `--` appends; a positional replaces up to the next `--`

As Option 2, but a `--` after the positional splits it: `paddock web -- --port=4096` runs
`web --port=4096`.

**Pros:** `--` has one meaning wherever it appears.
**Cons:** Strips a `--` the replacement command itself needed — `paddock git log -- file`
would run `git log file`. Passing a literal `--` then needs a second one, a rule nobody
would guess.

## Decision

Option 2. It implements the specified grammar, and for the unspecified case it matches
`docker run IMAGE COMMAND ARGS…`, where everything after the command belongs to it.
Option 3's uniform `--` costs the replacement command the ability to receive `--` at all
without an escape rule.

## Consequences

- `paddock -- <command> …` now runs `<agent command> <command> …`; invocations relying on
  the old replacement behaviour must drop the `--`. They launch the agent rather than
  failing: `paddock -- bash -c X` runs `claude bash -c X`.
- For the `false` agent, whose command is `/bin/bash`, args after `--` reach bash as a
  script path unless they start with an option such as `-c`; a replacement command is
  the usual form there.
- `ParsedArgs` carries `command` and `agent_args` separately, and at most one is non-empty;
  `DockerCommandBuilder.build` takes both.
- argparse's prefix matching is off; with it on, `--vol=/x:/y` was silently taken as
  `--volume=/x:/y`.
- An agent whose command is replaced still contributes its volumes and build args, so
  `paddock --agent=claude /bin/bash` is a shell in a Claude-configured container.
