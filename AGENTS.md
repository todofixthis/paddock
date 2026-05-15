> `CLAUDE.md` is a symlink to this file — edit `AGENTS.md` only.

## Getting Started

Before writing code, check:

- `docs/adr/INDEX.md` — prior decisions (don't re-litigate)
- `docs/future/` — deferred features (don't re-discuss)
- `docs/superpowers/plans/` — current implementation plan

## Architecture Decision Records

When making significant decisions — choosing between libraries, patterns, tools, or conventions — you **must** write an ADR before implementing the decision. Use the `writing-adrs` skill for the format and conventions. ADRs live in `docs/adr/`. Before writing, run `ls docs/adr/` to find the highest existing number and increment it.

If you find yourself about to establish a new cross-cutting pattern (something that will affect multiple domains or files, e.g. a testing convention, a shared utility, an error-handling approach), stop and write an ADR first even if the immediate task feels local. A pattern adopted once becomes the template for everything that follows.

## Commands

```bash
uv run autohooks activate --mode=pythonpath            # install pre-commit hook (once per clone)
uv add --bounds major <package>                        # add a runtime dependency at latest version
uv add --bounds major --group dev <package>            # add a dev dependency at latest version
uv sync --group=dev                                    # sync deps after pulling
uv run pytest                                          # run tests (current Python)
uv run tox -p                                          # run tests (all supported versions)
uv run pytest --collect-only                           # verify test count (note at start of mahi; confirm it increases when done)
uv run mypy src/                                       # type check
uv run ruff check                                      # lint
uv run make -C docs clean && uv run make -C docs html  # build docs
uvx --from pip pip index versions <package>            # check available versions on PyPI
uv run git commit                                      # always use instead of git commit (runs autohooks)
```

> **Never write bare `git commit` in plans or step-by-step instructions.** Autohooks requires the `uv run` prefix — a bare `git commit` will fail with "autohooks is not installed."

## Docstrings

Google/Napoleon format (`Args:`, `Returns:`, `Note:`) — not Sphinx `:param:` style. Max 80 chars per line. Escape backslashes (e.g. `'\\n'` not `'\n'`). Blank line before lists inside `Args:` sections to avoid Sphinx indentation warnings. ReadTheDocs treats all Sphinx warnings as errors — resolve them before pushing.

## Code Comments

Place comments on the line preceding the code they document, not as trailing comments.

## Language and Style

- NZ English; incorporate Te Reo Māori where natural (e.g. "mahi", "kaupapa")
- Use "Initialises" not "Initializes"

### Writing for coding agents

- Do not document information that already exists in the coding agent's training data or could be easily discovered by reading the code.
- Do not list individual files; list high-level directories so the agent knows where to look.
- Aim for concise style that optimises token count without sacrificing clarity.

## Branches

- `main` — releases only; merge from `develop` via PR
- `develop` — main development branch
- Feature branches off `develop` for all new work

## Configuration

- **`pyproject.toml` sections**: Keep all sections in alphabetical order — top-level tables (`[build-system]`, `[dependency-groups]`, `[project]`, `[tool]`) and subsections within each group (e.g. `[tool.autohooks]` before `[tool.hatch]` before `[tool.mypy]`).

## Architecture

- **Object-oriented implementation**: All implementation code (non-test) uses classes. Standalone functions are the exception, not the rule.
- **Flat test functions**: Tests are always flat functions (not methods on a class), even when testing class behaviour.
- **Naming convention**: Methods that produce a config dict from a specific source are named `config_from_<source>` (e.g. `config_from_env`, `config_from_cli`), not `<source>_to_config`.

## Testing

- **No lambdas in `pytest.mark.parametrize`**: if a parametrize case requires a lambda, that is a signal the cases are complex enough to deserve separate named test functions.

## Git Commits

Always commit via `uv run git commit`. Never use bare `git commit` — it bypasses autohooks and will fail. This rule applies in plan steps, commit instructions, and any other context where a commit command is written.

## Git Worktrees

Use `.worktrees/` for isolated workspaces (project-local, gitignored).

After switching to a worktree, run the autohooks activate command (see Commands) to install the pre-commit hook for that worktree.