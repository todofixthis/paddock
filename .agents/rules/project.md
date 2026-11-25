## Getting Started

Also check `docs/future/` for deferred features, and don't re-discuss them.

## Architecture

Paddock launches coding agents in isolated Docker containers. The package is `src/paddock/`: `agents/` holds the agent clients and servers, discovered through the `paddock.agents` and `paddock.servers` entry-point groups; `config/` loads and validates configuration from a registry of sources; `docker/` builds images and runs containers. `images/` holds the bundled Dockerfiles, one per agent.

- **Object-oriented implementation:** implementation code (not tests) uses classes. A standalone function is the exception, not the rule.
- **Naming:** a method that produces a config dict from a specific source is named `config_from_<source>` (`config_from_env`, `config_from_cli`), not `<source>_to_config`.
- **Registry-driven extensibility:** where a registry drives behaviour (config sources, agents), adding a member must take only a new class, with no edit to the orchestrator or to a shared constant. Let the registry own instantiation (`registry[key]`, not `cls()`), and put per-member metadata (defaults, weights, flags) on the member class rather than in a central lookup the orchestrator maintains.
- **Imports:** when two modules form a cycle, extract the shared symbol into a third module (as `errors.py` holds shared exception types); never defer an import into a function body to break it.

Every non-trivial function and method has a docstring explaining its purpose, including one whose implementation is simple but whose reason to exist isn't, such as a wrapper deferring evaluation to runtime.

Never carve a long function into labelled regions with banner or divider comments (`# ----`, `# Phase 3c: …`): extract each region into a well-named method instead.

In the template-owned `pyproject.toml`, paddock's own content is `[project]`'s dependencies, keywords and classifiers, the `paddock.agents` and `paddock.servers` entry points, the `paddock` script, `pytest-mock` in both the `dev` and `ci` groups, `images` in the sdist, the `paddock.config.filters` mypy override, and the RUF012 ignore. In the template-owned `renovate.json`, it is every custom manager but the phx-adr one, and every package rule but the template's "Never bump Python" rule. The `PYTHON_VERSION` rule must stay after that one, which it overrides for the Dockerfiles and `README.rst`: moved above it, the Dockerfiles' Python silently stops being bumped. Edit all of these here and keep them through a template-update conflict.

## CI

Paddock's own jobs are in `.github/workflows/project.yml`: `changes` and `image`, which build and smoke-test each bundled Dockerfile when a change touches the bundled images (ADR 016), and `readme`, which checks that PyPI renders `README.rst`. `.github/workflows/weekly.yml` calls the same workflow on a schedule, so a broken upstream input surfaces without a commit. A file that changes what the bundled images contain or how they're tested goes in `changes`' path list. A new bundled agent also needs, beside its `images/<agent>.Dockerfile` (ADR 022), an entry in `image`'s matrix, a `case` and usage lines in `.github/scripts/smoke-test.sh`, a `# renovate:` annotation above each `ARG` pin (the existing Dockerfile manager picks it up), and a custom manager for each pin `README.rst` repeats: without the matrix entry its Dockerfile is never built, and the check still passes.

## Docs

The docs landing page includes `README.rst`, so the README must render on GitHub, PyPI and Sphinx alike (ADR 025): link from it to a docs page by absolute URL on `/en/latest/`, and to a repository file by GitHub URL, never by relative path, which resolves differently in each. The user pages are RST under `docs/usage/`. Two changes in template-owned files are paddock's own, each with its comment: `README.rst` in the docs pre-commit hook's `INCLUDE`, and `html_css_files` in `docs/conf.py`.

## Releases

Where the `release` skill puts a migration guide's upgrade-alert bullet in both `README.rst` and `docs/index.rst`, put it in `README.rst` alone, linked by absolute URL on `/en/latest/` like any README link: `docs/index.rst` includes the README, so it lists the guide only in its `Reference` toctree (ADR 025), and the skill's check for the guide's name finds it there once, as a toctree entry, not an alert. The first guide creates the listing: a bullet list above the README's `contents` directive.

## Tests

Tests are flat functions, never methods on a class, even when testing class behaviour. Never put a lambda in `pytest.mark.parametrize`: cases that need one deserve separate named tests. Isolate a test from the environment by redirecting `$HOME` and stripping `PADDOCK_*` variables, not by patching Python internals such as module-level constants, so tests exercise the path resolution real users hit.

Run `uv run` from the repository root: it resolves the project from the working directory, so a command run from elsewhere fails with `ModuleNotFoundError: No module named 'paddock'`. Reference throwaway files by absolute path.

The existing tests predate `.agents/rules/testing.md`, and many have no docstring or a multi-line one; write new ones to its one-line rule.

## Python versions

The bundled Dockerfiles' `PYTHON_VERSION` (and its copy in `README.rst`) sets the containers' Python, not the range paddock supports: leave it alone when rotating Python versions, since Renovate bumps it.
