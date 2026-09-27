---
name: rotate-python-versions
description: Use when adding or dropping Python version support — updating requires-python, the CI test matrix, the all-versions test command, and docs to reflect a new set of supported versions.
---

# Rotate Python Versions

Update all version references consistently when adding or dropping Python support.

## Locations to update

- **`pyproject.toml`** — `requires-python` constraint and `Programming Language :: Python :: 3.x` classifiers
- **`uv.lock`** — regenerate with `uv lock` after changing `requires-python`, and commit it with the other edits; CI's `uv sync --locked` fails on a stale lockfile, and the all-versions test command doesn't catch it
- **`.github/workflows/`** — CI matrix `python-version` list
- **`docs/` and `README.rst`** — requirements/compatibility version list (not ADRs under `docs/adr/`, which record the versions at the time of each decision)
- **`AGENTS.md`** — the version list in the all-versions test command, and any version range mentioned in comments

## Key detail

Use `>=X.Y` for `requires-python`, not `~=X.Y` without a patch version — the tilde specifier without a patch (e.g. `~=3.12`) is ambiguous and triggers a uv warning.

Add a version only once it has a final release. Before making any edits, run `uv python list X.Y --only-downloads`: if every match carries an `a`, `b` or `rc` suffix (e.g. `cpython-3.15.0rc2`), the version isn't final, so ask the user how to proceed before touching anything.

Dependencies can lack wheels for a new version even after its final release. If the all-versions test command fails while installing dependencies (a source build error) rather than in the tests themselves, stop and ask the user; don't install system packages to make the build pass.

## After editing

Search for stray references:
```bash
rg "3\.\d{2}|py3\d{2}" . --glob "*.toml" --glob "*.yml" --glob "*.rst" --glob "*.md"
```

Then run the all-versions test command from `AGENTS.md`, with its updated version list, and confirm it exits 0.
