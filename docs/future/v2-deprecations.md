# v2 Deprecations

Behaviour kept in 1.x for compatibility, to remove in paddock 2.0. Delete each
entry once its removal lands, and this file with the last one.

## User config fallback to `~/.config/paddock/`

`ConfigContext.default_user_config_path` (`src/paddock/config/context.py`)
resolves the user config. When `XDG_CONFIG_HOME` is set to an absolute path and
`$XDG_CONFIG_HOME/paddock/config.toml` does not exist, it falls back to an
existing `~/.config/paddock/config.toml` and logs a deprecation warning ("Reading
user config from … This fallback is deprecated …"). When both files exist, it
reads the XDG one and logs a second warning ("Ignoring … because
XDG_CONFIG_HOME is set …").

### Suggested change

Remove only the fallback: with `XDG_CONFIG_HOME` set to an absolute path, read
`$XDG_CONFIG_HOME/paddock/config.toml` and nothing else.

Keep both warnings. They cost a stat each and point a user at the right file
when their local environment is misconfigured.

- **The both-files warning and its `samefile` guard stay as they are.** Keep the
  `samefile` call after both `exists()` checks: it raises `FileNotFoundError`
  when either path is missing.
- **Reword the fallback warning; don't merge it into the other one.** In this
  case the XDG file does not exist, so no user config is read at all, which is
  why the user's image and allowlist grants seem to vanish. The warning must say
  that `~/.config/paddock/config.toml` is ignored, that
  `$XDG_CONFIG_HOME/paddock/config.toml` does not exist so no user config was
  read, and to move the file there or unset `XDG_CONFIG_HOME`. Drop the
  "deprecated" wording.

Tests:

- `tests/config/test_context.py`: rename and rewrite
  `test_default_user_config_path_falls_back_to_legacy_with_warning` to assert
  the missing XDG path is returned, with the reworded warning. The other
  `default_user_config_path` tests stay as they are.
- `tests/config/test_loader.py`: rename and invert
  `test_resolve_falls_back_to_legacy_user_config`. With no user config loaded,
  `resolve()` raises `ExceptionGroup("config validation failed")` for the
  missing image, so either expect that or supply the image another way
  (`PADDOCK_IMAGE`) and assert the legacy file's image didn't win.

Docs:

- Rewrite the fallback paragraph in `default_user_config_path`'s docstring, which
  points here.
- `README.rst`, TOML files section, and `docs/usage/project-config.md`, the
  user-level bullet under Overview: drop the fallback.
- `docs/usage/project-config.md` Troubleshooting: replace the fallback warning's
  entry with the reworded one. Under `[final:image] Non-empty value expected.`
  and `project_toml: dropped non-allowlisted keys …`, note that with
  `XDG_CONFIG_HOME` set, paddock reads only `$XDG_CONFIG_HOME/paddock/`, since
  those are the errors a skipped legacy file produces.
- Release notes (written through the `release` skill, published as the GitHub
  release): list the removal under breaking changes, naming the 1.x release that
  added the fallback and noting that `--quiet` hid its warning.

### Why deferred

Users who already set `XDG_CONFIG_HOME` for other tools keep paddock's config in
`~/.config/paddock/`. Removing the fallback in 1.x would stop that config loading
on upgrade, which is a breaking change.
