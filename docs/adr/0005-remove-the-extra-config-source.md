---
status: Accepted
date: 2026-09-08
scope: [src/paddock/cli.py, src/paddock/config/sources/, docs/usage/project-config.md, tests/]
summary: Delete the extra config source (--config-file / PADDOCK_CONFIG_FILE) rather than keep it speculative.
revisit-when: A concrete need for a runtime-named config file emerges.
---

# 0005: Remove the Extra Config Source

## Context

`ExtraConfigSource` was introduced alongside the rest of the [0003][] registry —
one more `ConfigSource` subclass, loading a user-shaped TOML file named at runtime via
`--config-file` / `PADDOCK_CONFIG_FILE`. It shipped speculatively, without a driving use
case, on the reasoning that the registry made a source cheap to add.

That reasoning holds for cost of addition; it says nothing about whether a source earns
its place in the precedence order once added. `ExtraConfigSource` sits at a fixed
`WEIGHT = 40`, between `project_overrides` (30) and `env` (50) — a position nothing
motivates, since no requirement ever fixed where a runtime-named file should outrank
project overrides but lose to environment variables. Anyone reasoning about precedence
today has to account for a source whose place in the order is arbitrary, alongside
`user`, `project_toml`, `project_overrides`, `env`, and `cli`, each of which does have a
clear precedent (user defaults, project settings, per-project overrides, and the
conventional env-then-CLI order).

No production caller or issue has ever needed `--config-file` / `PADDOCK_CONFIG_FILE` —
every place it's exercised is a test: that source's own suite, tests elsewhere that name
it directly (CLI parsing, loader precedence, registry weight order), or the
`config_file=None` fixture value every other source test carries for `ParsedArgs`.
Keeping an unused, arbitrarily-ordered source costs every future reader of the
precedence table more than it has ever bought a user.

## Options

### Option 1: Do nothing

**Pros:** No migration; existing (hypothetical) users of `--config-file` keep working.
**Cons:** The precedence table keeps a source with no motivating use case and no
justified position in the weight order, for every reader who reasons about it from now
on.
**Risks:** A source scaffolded once anyway attracts anchoring — future work
"just extends" `ExtraConfigSource` instead of asking whether its precedence still fits.

### Option 2: Delete the source (Accepted)

Remove `ExtraConfigSource`, its registration, the `--config-file` CLI flag, the
`config_file` field on `ParsedArgs`, and `PADDOCK_CONFIG_FILE` handling. Reintroduce a
comparable source only once a concrete need fixes its shape and its place in the
precedence order.

**Pros:** The precedence table shrinks to sources with an established rationale for
their position; nothing left to explain away.
**Cons:** A real future need for a runtime-named config file starts from zero design
work instead of an existing (if unmotivated) implementation.
**Risks:** None beyond the deferred design cost above and the test churn — no
production caller is affected.

### Option 3: Keep the source but fix its weight to the network boundary

Keep `ExtraConfigSource`, but redefine its `WEIGHT` to sit adjacent to `env`/`cli` (both
of which the [project-config][] threat model already treats as trusted, on the same
"already requires shell control" reasoning) rather than between `project_overrides` and
`env`.

**Pros:** Gives the fixed-weight question a principled answer instead of leaving it
arbitrary.
**Cons:** Still speculative — repositioning an unused source does not supply the missing
use case, and a fixed weight is only one of the open design questions the kaupapa
(purpose) raised (whether an extra file should inherit the precedence of whichever
source names it, for instance, is untouched by this option).

## Decision

Option 2. The open design questions — fixed weight vs. inherited precedence, whether
more than one extra file should be nameable — stay unanswerable in the abstract. A
concrete use case would answer them by construction; today none exists to ask.

## Consequences

- `docs/usage/project-config.md`'s precedence table drops from six sources to five;
  its allowlist section's "sources with no allowlist entry" note drops `extra` from the
  list, leaving `user` and `project_overrides`.
- [0004][]'s subsidiary decision that `extra` and `project_overrides` stay trusted and
  non-restrictable no longer has `extra` to apply to; the decision itself needs no
  change, since `project_overrides` still stands as its subject.
- `--config-file` and `PADDOCK_CONFIG_FILE` become unrecognised; no deprecation path is
  provided, since neither had a known production caller.
- `tests/config/sources/test_extra.py` is deleted along with the source it tests. Every
  test elsewhere naming `config_file` or `extra` directly — CLI parsing
  (`tests/test_cli.py`), loader precedence (`tests/config/test_loader.py`), registry
  weight order (`tests/config/sources/test_base.py`) — is updated to drop it; every
  other source test's `ParsedArgs` fixture drops its `config_file=None` field.

[0003]: 0003-registry-driven-config-sources.md
[0004]: 0004-allowlist-over-denylist.md
[project-config]: ../usage/project-config.md
