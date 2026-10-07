> **Symlinks for Claude Code compatibility:**
> - `CLAUDE.md` → `AGENTS.md` — edit `AGENTS.md` only
> - `.claude/skills/` → `.agents/skills/` — edit skills under `.agents/skills/` only
>
> `.claude/` is a real directory (`settings.json` plus the `skills` symlink); only
> `.claude/skills` symlinks into `.agents/skills`. Keep `.claude/` a real directory —
> the native worktree tool refuses to run against a committed `.claude` symlink. Git
> refuses to stage files through a symlink directory, so stage skills and `AGENTS.md`
> via their real paths (`.agents/skills/`, `AGENTS.md`), never the symlink paths.

## Getting Started

Before writing code, check:

- `docs/adr/INDEX.md` — prior decisions (don't re-litigate)
- `docs/future/` — deferred features (don't re-discuss)
- `docs/superpowers/plans/` — the implementation plan in progress, if any (removed once its mahi lands)

## Architecture Decision Records

When making significant decisions — choosing between libraries, patterns, tools, or conventions — you **must** write an ADR before implementing the decision. Use the `phx:writing-adrs` skill (from the phx plugin, which `.claude/settings.json` enables) for the format, conventions and tooling: its `adr.py` allocates the number, generates `docs/adr/INDEX.md` and validates the corpus. Outside Claude Code, run the same tool as `phx-adr` (see Commands). Don't hand-edit the index or add a repo-local ADR script (ADR 009). ADRs live in `docs/adr/`.

If you find yourself about to establish a new cross-cutting pattern (something that will affect multiple domains or files, e.g. a testing convention, a shared utility, an error-handling approach), stop and write an ADR first even if the immediate task feels local. A pattern adopted once becomes the template for everything that follows.

## Commands

```bash
uv run autohooks activate --mode=pythonpath            # install pre-commit hook (once per clone)
uv add --bounds major <package>                        # add a runtime dependency at latest version
uv add --bounds major --group dev <package>            # add a dev dependency at latest version
uv sync --group=dev                                    # sync deps after pulling
uv run pytest                                          # run tests (current Python)
uv run tox run-parallel                                # run tests (all supported versions)
uv run pytest --collect-only                           # verify test count (note at start of mahi; confirm it increases when done)
uv run mypy src/                                       # type check
uv run ruff check                                      # lint
uvx --from pip pip index versions <package>            # check available versions on PyPI
uv run make -C docs html SPHINXOPTS="-W --keep-going -E"  # build docs strictly (-E: full re-read, else a rerun hides warnings)
uv run git commit                                      # always use instead of git commit (runs autohooks)
```

The phx plugin's ADR tool, for use outside Claude Code, where the [`writing-adrs` skill](https://github.com/todofixthis/phx-claude-siat/blob/8.1.0/skills/writing-adrs/SKILL.md) states the conventions. Renovate bumps these pins and the `adrs` CI job's together (ADR 010), matching each on its trailing `# X.Y.Z` comment — keep that comment on the same line, despite the Code Comments rule below; moved or dropped, that pin silently stops being bumped.

If CI reports a stale index the session's own tool can't reproduce, the installed plugin and the pinned release differ. Compare the two versions: if the installed one is newer, merge Renovate's pending bump, or bump by hand: each pin to the release's commit, and its comment and the skill link above to the release's version. The commit is the `refs/tags/<version>^{}` line of `git ls-remote --tags https://github.com/todofixthis/phx-claude-siat`, not the tag object above it. Otherwise update the plugin.

```bash
# Scaffold the next ADR
uvx --from 'git+https://github.com/todofixthis/phx-claude-siat@0725567cec6bab6a227c2a3d569e64c226c33a4e#subdirectory=skills/writing-adrs' phx-adr new "Title" --summary "…" --scope path/ # 8.1.0
# Regenerate docs/adr/INDEX.md
uvx --from 'git+https://github.com/todofixthis/phx-claude-siat@0725567cec6bab6a227c2a3d569e64c226c33a4e#subdirectory=skills/writing-adrs' phx-adr index # 8.1.0
# Validate, as CI does
uvx --from 'git+https://github.com/todofixthis/phx-claude-siat@0725567cec6bab6a227c2a3d569e64c226c33a4e#subdirectory=skills/writing-adrs' phx-adr check # 8.1.0
```

> **Run `uv run` from the repo (or worktree) root** — it resolves the project from the working directory, so `cd`-ing to a scratchpad first breaks imports with `ModuleNotFoundError: No module named 'paddock'`. Keep the cwd at the root and reference throwaway files by absolute path.

## Docstrings

Google-style format (`Args:`, `Returns:`, `Note:`) — not the `:param:` field-list style. Max 80 chars per line. Escape backslashes (e.g. `'\\n'` not `'\n'`). Blank line before lists inside `Args:` sections.

All non-trivial functions and methods require a docstring explaining their purpose. This includes cases where the reason for a function's existence is non-obvious even if its implementation is simple — e.g. a wrapper that defers evaluation to runtime.

## Code Comments

Place comments on the line preceding the code they document, not as trailing comments.

**No divider comments.** Never use banner/section-divider comments (e.g. `# ----` or
`# Phase 3c: ...`) to carve a long function into labelled regions. The need for one is a
smell that the function is doing too much — extract each labelled region into its own
well-named method instead.

## Language and Style

- NZ English; incorporate Te Reo Māori where natural (e.g. "mahi", "kaupapa")
- Use "Initialises" not "Initializes"

### Writing for coding agents

- Do not document information that already exists in the coding agent's training data or could be easily discovered by reading the code.
- Do not list individual files; list high-level directories so the agent knows where to look.
- Aim for concise style that optimises token count without sacrificing clarity.

## Branches

`develop` is the default and development branch: feature branches come off it, and pull requests target it. `main` carries releases only. Changes reach it through the `release` skill, as a release branch off `develop` or a hotfix branch off `main`, and every release ends by merging `main` back into `develop`. A clone made before `develop` became the default still has `origin/HEAD` on `main`; run `git remote set-head origin -a` once to fix it.

## Configuration

- **`pyproject.toml` sections**: Keep all sections in alphabetical order — top-level tables (`[build-system]`, `[dependency-groups]`, `[project]`, `[tool]`) and subsections within each group (e.g. `[tool.autohooks]` before `[tool.hatch]` before `[tool.mypy]`).

## Architecture

- **Object-oriented implementation**: All implementation code (non-test) uses classes. Standalone functions are the exception, not the rule.
- **Flat test functions**: Tests are always flat functions (not methods on a class), even when testing class behaviour.
- **Naming convention**: Methods that produce a config dict from a specific source are named `config_from_<source>` (e.g. `config_from_env`, `config_from_cli`), not `<source>_to_config`.
- **Registry-driven extensibility**: where a registry drives behaviour (e.g. config sources, agents), adding a new member must require only defining a new class — no edits to the orchestrator or to any shared constant. Let the registry own instantiation (`registry[key]`, not `cls()`), and push per-member metadata (defaults, weights, flags) onto the member class rather than into a central lookup the orchestrator maintains. A constant the orchestrator must update for each new member is the anti-pattern this rule exists to prevent.

### Imports

Prefer restructuring module boundaries over deferring imports. If two modules cycle, the
right fix is to extract the shared symbol into a third module (e.g. `errors.py` for shared
exception types). Do not use function-body `import` statements as a workaround.

## Testing

- **No lambdas in `pytest.mark.parametrize`**: if a parametrize case requires a lambda, that is a signal the cases are complex enough to deserve separate named test functions.
- **Environment-level isolation**: prefer redirecting `$HOME` and stripping env vars (e.g. `PADDOCK_*`) over patching Python internals (e.g. module-level constants). This keeps tests honest — they exercise the same path-resolution logic real users hit.

## Git Commits

Always commit via `uv run git commit`, never bare `git commit` — the bare form bypasses autohooks and fails with "autohooks is not installed". This applies everywhere a commit command is written, including plan steps and instructions.

## Git Worktrees

Use `.agents/worktrees/` for isolated workspaces (project-local, gitignored).

After switching to a worktree, run the autohooks activate command (see Commands) to install the pre-commit hook for that worktree.