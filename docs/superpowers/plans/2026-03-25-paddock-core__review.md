Reviewer feedback for @docs/superpowers/plans/2026-03-25-paddock-core.md:

# Meta
## Additional Convention: Worktree Name in Plan Header

After the worktree is created (by the brainstorming skill), add a `**Worktree:**` field to the plan header so executing agents know where to work:

```markdown
**Worktree:** `path/to/worktree` (branch: `feature/branch-name`)
```

If the plan is written before the worktree exists, add a first step to the first task:

```markdown
- [ ] **Step 1: Record worktree path**

Run: `git worktree list`
Update the `**Worktree:**` field in this plan's header with the path and branch name, then save.
```

Add this to every task in the self-review checklist too: "Does the plan header include a `**Worktree:**` field?"

## Additional Convention: Plan Compression Step

Every task must end with a compression step as its final item:

```markdown
- [ ] **Step N: Compress this task in the plan**

Replace this task's full section with a one-paragraph summary of what was done, then commit the plan update using the `creative-commits` skill.
```

Add this to every task in the self-review checklist too: "Does every task end with a compression step?"

### What a good compression preserves

Once a task is complete, its detailed instructions are noise for future agents working on later tasks. The paragraph summary should carry forward only what matters to subsequent work:

**Keep:** what was built and where it lives (file names, types, key functions); decisions that constrain or inform later tasks; patterns later tasks should follow.

**Drop:** step-by-step instructions, code samples (they're in the committed code now), commands, test scaffolding.

**Good example:**
> `SecurityHolding` type added to `shared/types/securities.ts`. `getHoldings()` implemented in repository (CTE aggregating purchases and income, filtering voided rows) and service (adds `breakEvenPriceLocalCurrency = netActualPositionUsd / rate / sharesHeld`, null when `sharesHeld === 0`). Route registered at `GET /api/v1/securities/holdings` before `/:id/*` routes.

**Too thin (loses context):**
> Task 5 done. Holdings endpoint implemented.

The compression commit is separate from the implementation commit — both use the `creative-commits` skill.

# Plan feedback
## (general)

- Let's rewrite the entire implementation to be object-oriented please.
  - Tests remain flat functions though.
  - Please document these conventions in `AGENTS.md`.
- Let's change up the way we parse configs:
  - Single class for configuration.
  - One method for each configuration source (user-level file, project-level file, env vars, CLI args).
    - Each method should return a result that conforms to the same `TypedDict` structure.
    - Each property in the return value should have a `value` and a `source` so that it's easier to diagnose configuration errors.
      - These can be stored together or separately so long as it's easy to correlate a `value` with its `source`.
  - Additional method as the entry point for resolving the overall configuration (runs the methods to load the config from each source, deep-merges them together, and inits the `FilterRunner` for validation.
    - Offload merging, validation, etc. to private methods to avoid overloading this method with responsibilities.
    - Returns the `FilterRunner` instance so that the caller can confirm the validation passed and surface the validation errors if not.
- Let's add a `--workdir` flag which allows the user to specify a different workdir directory than `cwd`.
- Let's also add `PADDOCK_CONFIG_FILE` env var and `--config-file` CLI arg that allow injecting arbitrary config files into the hierarchy. The resolution works like this (config from later sources overwrites config from earlier sources):
  1. User-level (`~/.config/paddock/config.toml`) is still loaded first.
  2. Then project-level `config.toml`.
  3. Then `PADDOCK_CONFIG_FILE` if specified.
  4. Then `--config-file` if specified.
  5. Then env var overrides applied.
  6. Lastly CLI arg overrides applied.

## Task 1: Project Scaffolding

- Do not specify dependencies in `pyproject.toml`; instead use `uv add` with major version bounds.
- I've copied the `pyproject.toml` file from a different project. Use it as inspiration for planning the metadata for this project so that we have consistency across all of our Python projects. Incorporate relevant configuration and metadata into the plan, then remove the `pyproject.toml` file so that the coding agent replaces it during the build.

## Task 2: Config Schema (`phx-filters`)

- Tests are a great source of documentation. Let's ensure that tests have docstrings and/or comments where appropriate to help explain the behaviour under test. For example, `test_valid_volumes` could be clarified to explain that it's proving different ways to specify a volume (also that test should probably also include an explicit `:ro` mode in addition to implicit `:ro` and explicit `:rw`).
  - Do a review of the tests and consider whether we can improve them for better coverage and improve their function as documentation
- Pattern for all filter chains:
  1. `f.Required` if required, and omit `f.Optional` at the start of the chain (see point 4).
  2. Type check/coercion (e.g. `_build_schema['policy']` should be `f.Unicode | ...`, `_config_schema['build']` should be `f.Type(dict) | _build_schema`, etc.)
  3. Additional filters
  4. If the chain has a default value, put `f.Optional(default_value)` at the end of the chain so that the default value doesn't get validate (assumption is the developer either specified a default value that would pass validation...or they deliberately picked a default value that doesn't conform to make it detectable in downstream logic)
- Let's define a couple of custom filters (and corresponding tests) for the following validation:
  - `Volume` (applies the `_volume_value` filter chain, then appends `:ro` if needed)
  - `Agent` (`f.Type((bool, str))`, map `"false"` to `False`, if boolean must not be `True`)
    - Note: don't include `f.Required` in custom filters, as that's not specific to validating individual values; instead callers will chain them together e.g. `f.Required | Agent`
  - Developing custom filters could be done as its own Task in between Project Scaffolding and Config Schema.
- For the `build` config, let's also add an `args` table that can contain any key-value pair.
  - We can use `f.FilterRepeater` to apply `f.Unicode` to all the values in the mapping.
  - The user can specify their own dockerfile which could accept any arbitrary args, so don't restrict which args can be included in the configuration.
  - Let's see if we can make build args can overridden via env vars e.g. `PADDOCK_BUILD_ARGS_FOO=BAR`
  - Ideally these should also be configurable via CLI args e.g. `--build-args-foo=bar`

## Task 3: Config Loader

- When including fixtures in test functions, please add type hints.

## Task 4: Env Var Mapper

- Can any of these tests be parametrised?
  - That would also give us an opportunity to concisely document all the available env vars
- Please rename `env_to_config` to `config_from_env`  and document the `result_from_source` instead of `source_to_result` convention in AGENTS.md.
- Let's explore a version of that function that works dynamically instead of hard-coding env vars (i.e. iterate over `PADDOCK_*` env vars, chop off the prefix, convert to lowercase, and deep-map to the corresponding `config` value).

## Task 5: CLI Argument Parser

- Let's also allow specifying build config via CLI flags (e.g. `--build-dockerfile=...`, `--build-context=...`, etc.).
- Add a docstring to each test describing the use case. That way the tests do double duty as documentation--not just what happens but how a user might leverage that behaviour when invoking paddock.
  - In particular, `test_positional_becomes_command` needs a docstring to make it clearer what's going on. A developer might not understand readily that `claude` gets interpreted as a program name not the agent, and `--agent` gets treated as a flag passed to the `claude` program rather than a paddock argument. Though potentially confusing, this is meant to be an optimisation to save the user the hassle of having to add `--`.
- Let's add a variant before `test_paddock_flag_before_positional` that documents that `--agent=opencode claude --agent=plan` is not a valid use case.
  - We don't have to bend over backwards to support this use case; `ArgumentParser` is going to merge the two `--agent` flags together before it gets to `parse_args`, and that's OK--we'll just use the test to document that the user has to use `--` to disambiguate (i.e. `parse_args['--agent=opencode', '--', 'claude', '--agent=plan'])` is the valid use case).
- Let's modify `test_unknown_flag_passes_through` to show that the unknown flag also acts as an implicit `--` e.g. `--resume --agent=plan` means the `--agent` flag is not interpreted as a paddock argument.
- Do we need to include tests for putting `--` in weird places?
  - Examples:
    - More than one occurrence of `--` (e.g. `--agent=opencode -- --continue -- auth login`)
    - `--` after a positional argument (e.g. `--agent=opencode web -- --port=4096`)
    - `--` after an unknown argument (e.g. `--agent=opencode --fork -- --continue`)
  - Similarly to the ambiguous `--agent` case above, let's not introduce extra complexity to try to support these edge-on-edge cases; just use the tests to document what happens.
- In the `_parse_volume` docstring, let's also mention why we're not using `_volume_value` (the `--volume` CLI arg uses a different format than `config.toml`).

## Task 6: Agent Base Class and Registry

- I think we can omit the unit tests for this task, as they are really just testing the behaviour of `EntryPointClassRegistry` which already has its own test case.
- Move `BaseAgent` into `src/paddock/agents/__init__.py` so that it can use `AutoRegister(agent_registry)` as its base class
- Let's add example values to each method docstring in `BaseAgent`.

## Task 7: ShellAgent

- I think we can omit unit tests for this task, as they're just confirming a static return value; there's no real logic to test.

## Task 8: ClaudeAgent

- Same as for task 7: there's not really any complex logic here that needs testing.

## Task 9: Docker Command Builder

- Let's name the container after the working directory when the user invokes the command. For example, if the user runs the paddock command in `~/Documents/Portfolio` then the container is named `paddock-portfolio-claude`
  - If the container name is already taken, append a numeric suffix e.g.`paddock-portfolio-claude-1`
  - Make the check only once before generating the command. We'll accept the race condition that the user could spin up another container with a conflicting name in between.
- In `test_minimal_command` let's document each assertion (i.e. why does that value need to be present in `argv`) so that the test better serves as documentation.
- `test_config_volumes` has an unused `idx` variable.
- The workdir path in the container should match `cwd` not `/workspace`.
  - E.g. if `cwd` is `/Users/phx/Documents/paddock`, then the workdir should also be that path inside the container.
  - This is important because many coding agents store project-level configuration based on the filepath, so it needs to be identical between host and container.

## Task 10: Image Auto-Build

- Have `get_image_created_at` leverage `f.DateTime()` for the ISO -> `datetime` conversion.

## Task 11: Main Entry Point

- Rework the tests so that they verify two behaviours:
  - What was the output?
    - We might consider a test helper for validating the output, so that we can share logic between tests. It will also help the tests to serve as documentation, since the helper lays out what the command typically outputs.
  - Did the `docker` command get invoked.
- E.g. `test_dry_run_exits_zero` should also confirm that the `docker` command was **not** invoked.
- Make `test_quiet_suppresses_logs` more aggressive — there should be no output at all.
- We also need a test for the `--help` flag.
- If the user provides a network, let's have paddock also log the names of other containers that are currently running on that network. This will help developers to troubleshoot network connectivity issues.
- Just to confirm, if `maybe_build` triggers a build, the `docker build` subprocess output needs to be visible to the user.
  - The log output should also confirm whether a build was triggered or skipped (only applicable if there is a `build` configuration).

## Task 12: Base Dockerfile

- Can we make the Ubuntu and Node versions configurable via docker build args?
- Do we need to use quotes in the `apt-get` command when injecting `${PYTHON_VERSION}` (we assume it will be something like `3.13`, but it could be any arbitrary string--if a malicious argument gets injected we want the build to error instead of running arbitrary commands).

# Post-review
- Use what you've learned about working with `phx-filters` to write a skill to help teach coding agents how to work with that library (usage instructions, patterns for chaining filters, when to compose vs when to write a custom filter, etc.).
  - Only document information that's not readily available by reading the source code and documentation for the `phx-filters` library