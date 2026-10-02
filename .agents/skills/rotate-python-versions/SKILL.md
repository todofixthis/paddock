---
name: rotate-python-versions
description: Use when adding or dropping Python version support — updating requires-python, tox environments, the CI test matrix, and docs to reflect a new set of supported versions.
---

# Rotate Python Versions

Update all version references consistently when adding or dropping Python support.

## Locations to update

- **`pyproject.toml`** — `requires-python` constraint, `Programming Language :: Python :: 3.x` classifiers and `[tool.tox]` `env_list`
- **`uv.lock`** — regenerate with `uv lock` after changing `requires-python`, and commit it with the other edits; CI's `uv sync --locked` fails on a stale lockfile
- **`.github/workflows/`** — CI matrix `python-version` list (each entry must match a tox environment)
- **`docs/` and `README.rst`** — requirements/compatibility version list (not ADRs under `docs/adr/`, which record the versions at the time of each decision)
- **`AGENTS.md`** — any version range mentioned in comments

## Key detail

Change only the lower bound of `requires-python` and keep the rest of the specifier (e.g. the `, <4` cap). Use `>=X.Y`, not `~=X.Y` without a patch version — the tilde specifier without a patch (e.g. `~=3.12`) is ambiguous and triggers a uv warning.

Add a version only once it has a final release. Before making any edits, run `uv python list X.Y --only-downloads`: if every match carries an `a`, `b` or `rc` suffix (e.g. `cpython-3.15.0rc2`), the version isn't final, so ask the user how to proceed before touching anything.

Required status checks are named per matrix entry (`test (3.12)`), and no file records which ones branch protection requires. Ask the user whether any name a version you are dropping or adding: a required check for a dropped version never reports and blocks every PR.

Dependencies can lack wheels for a new version even after its final release. If `uv run tox run-parallel` fails while installing dependencies (a source build error) rather than in the tests themselves, stop and ask the user; don't install system packages to make the build pass.

## After editing

Search for stray references. `--hidden` is needed to reach `.github/workflows/`, so the `!` globs keep out the directories it would otherwise add:
```bash
rg -n "3\.\d{2}|py3\d{2}" . --hidden --glob "*.toml" --glob "*.yml" --glob "*.rst" --glob "*.md" --glob "!uv.lock" --glob "!docs/adr/**" --glob "!.git/**" --glob "!.venv/**" --glob "!.tox/**"
```

Expect noise from dependency pins (e.g. `pytest-mock>=3.15.1`) and from skill files that mention versions in prose. Leave the Docker image's `PYTHON_VERSION` default (`images/Dockerfile`, and its mentions in `README.rst`) alone: it sets the container's Python, not the supported range. When dropping a version, every remaining hit for it should be one of those.

Then run `uv run tox run-parallel` and confirm it exits 0.
