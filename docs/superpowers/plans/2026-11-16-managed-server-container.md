# Managed Server Container Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A run that chooses an installed server starts that server's shared
container if it is not running, waits for it, and connects a paired client to it.

**Architecture:** ADR 019 is the specification. `ManagedContainer` owns one named,
labelled, long-lived container and knows nothing about agents. `ServerLauncher`
turns a `BaseServer` and its validated settings into that container, mints or reads
back its secret, and returns a `ServerConnection`. `DockerCommandBuilder` connects a
paired client. No server is bundled yet: OpenCode and the user docs are the next pull
request, so this one is proven with fake servers in unit tests and a stand-in server
against real Docker. Completed pre-work: ADRs 018, 019 and 020 are on `develop`; this
plan file is committed.

**Tech Stack:** Python, Docker CLI through `subprocess`, phx-filters,
phx-class-registry, pytest with pytest-mock.

**Spec:** `docs/adr/019-run-one-shared-container-per-agent-server.md` (all of it) and
`docs/adr/018-split-agents-into-clients-and-servers.md` (its Pairing paragraph and
Consequences). The wider design is
`docs/superpowers/specs/2026-11-15-agent-client-server-design.md`.

**Worktree:** `/home/user/paddock` (branch: `claude/laughing-knuth-e8mouz`). A cloud
session's container is already isolated and may push only to this branch, so no
separate worktree exists.

## Global Constraints

- One container per server key, named `paddock-server-<key>`, on a bridge network of
  the same name. Both carry the label `paddock.managed=server:<key>`. A container or
  network of that name without that label stops the run.
- `docker run -d`, with no `--rm` and no restart policy. Paddock never stops,
  restarts or force-removes a server. A stopped one is removed by the container ID
  that was observed, without `-f`, and recreated; a failed removal means another
  Paddock got there first and is not an error.
- A concurrent Paddock that loses the race for the name treats the server as
  starting and waits for readiness like any other.
- The run spec lives in labels: `paddock.spec-hash` (image, command, mounts,
  environment variable *names*, container port, requested host port) and
  `paddock.volumes` (the mounts as JSON). Drift between the label and config warns,
  prints `docker rm -f paddock-server-<key>`, and uses the running server.
- The port is published on `127.0.0.1` only: the configured `port`, or one Docker
  assigns, read back with `docker port`.
- The secret is minted when the container is created (`secrets.token_urlsafe(32)`),
  set in its environment as `PADDOCK_SERVER_SECRET` beside whatever
  `BaseServer.get_env(secret)` returns, and read back with `docker inspect` on later
  runs. It reaches Docker as `-e NAME` with the value in the subprocess environment,
  and never appears in a printed or logged command.
- Readiness: poll `BaseServer.is_ready(connection)` every half second for up to 30
  seconds. On timeout, or if the container stops first, stop the run with a pointer
  to `docker logs paddock-server-<key>` and leave the container.
- A server's image is built or pulled under its `build` settings only when the
  container is about to be created.
- A server's settings are checked on disk only when that server is chosen: every
  volume host path and build path must exist; a `~` first segment is expanded.
- The workdir check applies only to a paired client and a server with
  `REQUIRES_WORKDIR_MOUNT`: of all the server's mounts, its own included, the one
  whose container path most specifically covers the workdir must be read-write and
  have that container path as its host path. A running server is judged by its
  `paddock.volumes` label, a server about to be created by its spec.
- A paired client joins the server's network in addition to any configured
  `network`; a configured `host`, `none` or `container:…` stops a paired run. An
  unpaired client beside a server gets no network, no environment and no arguments
  from it, and the log says the two are not connected.
- `--dry-run` runs every check, prints the server's `docker run` line where the
  container would be created, and creates, builds, pulls, removes and mints nothing.
  An unassigned host port prints as `<port>`.
- Everything that consults a registry takes it as a keyword argument. Tests stub
  `subprocess.run` per module, as `tests/docker/test_pull.py` does; no test starts a
  container.
- Commit with `uv run git commit`, from the repo root. NZ English. Flat test
  functions, no lambdas in `parametrize`, Google-style docstrings, comments on the
  line above, implementation in classes. Every new public module is listed in
  `docs/api.rst`, or the strict docs build in the pre-commit hook fails.
- The suite collects 450 tests before this plan; the count must rise.

## Review Focus

1. A server image that exits at once (wrong image, no such binary): the run stops
   within the readiness window naming `docker logs`, the dead container is kept,
   and the next run removes it and tries again. Task 3.
2. A user-level volume whose host path does not exist, for a server the run does
   *not* choose: the run is unaffected. For the chosen server it is a config error
   naming the path. Task 1.
3. A workdir under a mount declared `ro`, or shadowed by a more specific mount of
   another host path: the run stops before any client starts. Task 3.
4. Two runs starting the same server at once, and a stopped container two runs both
   try to remove: neither fails, and both read the one secret. Tasks 2 and 3.
5. The secret: absent from the printed `docker run` lines, from `--dry-run` output
   and from every log record. Tasks 3 and 4.
6. A container named `paddock-server-<key>` that Paddock did not create: the run
   stops and does not remove or adopt it. Tasks 2 and 3.

## File Map

- `src/paddock/config/`: `loader.py`, new `server_settings.py`.
- `src/paddock/docker/`: new `managed.py`, new `server.py`, `builder.py`.
- `src/paddock/__main__.py`, `docs/api.rst`.
- `tests/config/`, `tests/docker/`, `tests/test_main.py`.

---

### Task 1: Check the chosen server's settings

**Files:**
- Create: `src/paddock/config/server_settings.py`
- Modify: `src/paddock/config/loader.py`
- Test: `tests/config/test_server_settings.py`, `tests/config/test_loader.py`

**Interfaces:**
- Produces, in `paddock.config.server_settings`:
  ```python
  @dataclass(frozen=True)
  class ServerSettings:
      image: str
      build: dict | None
      port: int | None
      volumes: dict[str, VolumeSpec]

      @classmethod
      def from_config(cls, settings: dict, *, key: str, default_image: str | None) -> "ServerSettings": ...
  ```
  `settings` is the merged `config["agents"][key]["server"]` table, or `{}`.
  `volumes` is keyed by the host path with `~` expanded and symlinks resolved.
  `build`, where present, is `{"args": dict, "context": Path | None, "dockerfile":
  Path, "policy": str}` with the same defaults `ConfigLoader._apply_defaults` gives
  top-level `build`, both paths expanded and resolved; it is `None` when the table
  has no `dockerfile` and no `policy`.
  It raises `ExceptionGroup("config validation failed", [ConfigError, ...])`, one
  `ConfigError` per problem, each message `[agents.<key>.server.<path>] <message>`.
- Produces, on `ResolvedConfig`: `server_settings: ServerSettings | None`, set when
  `server_key` names a server in the injected registry, else `None`.

- [ ] **Step 1: Write the failing tests**

  `tests/config/test_server_settings.py`, calling `from_config` with
  `key="srv"`:
  - `test_settings_resolve_volumes_and_image`: with a real `tmp_path` directory `d`,
    `{"image": "img", "volumes": {str(d): VolumeSpec(str(d), "rw")}}` gives
    `image == "img"`, `volumes == {str(d.resolve()): VolumeSpec(str(d), "rw")}`,
    `build is None`, `port is None`.
  - `test_default_image_fills_a_missing_image`: `{}` with
    `default_image="base"` gives `image == "base"`.
  - `test_configured_image_beats_the_default`.
  - `test_missing_image_without_a_default_is_an_error`: `{}` with
    `default_image=None` raises; the message is exactly
    `[agents.srv.server.image] No image is set, and server "srv" has no default`.
  - `test_missing_volume_path_is_an_error`: a host path that does not exist raises
    with a message starting `[agents.srv.server.volumes./no/such] `.
  - `test_tilde_volume_is_expanded`: with `$HOME` at `tmp_path` and a directory
    `tmp_path / "Dev"`, the key `~/Dev` resolves to `str((tmp_path / "Dev").resolve())`.
  - `test_build_paths_must_exist`: a missing `dockerfile` raises at
    `[agents.srv.server.build.dockerfile]`; a missing `context` at
    `[agents.srv.server.build.context]`.
  - `test_build_defaults_match_the_top_level_build`: `{"image": "i", "build":
    {"dockerfile": <real file>}}` gives `build == {"args": {}, "context": None,
    "dockerfile": <resolved Path>, "policy": "if-missing"}`.
  - `test_port_is_carried`: `{"image": "i", "port": 4096}` gives `port == 4096`.
  - `test_every_problem_is_reported`: a missing volume and a missing dockerfile
    together raise two `ConfigError`s.

  `tests/config/test_loader.py`, with the fake registries already in that file
  (add `DEFAULT_IMAGE = "srv-default"` to a new fake server `srv`, and reuse the
  `paired` client whose `DEFAULT_SERVER` is `"srv"`):
  - `test_chosen_server_settings_are_resolved`: `agent = "paired"` and
    `[agents.srv.server] image = "img"` gives
    `r.server_settings.image == "img"`.
  - `test_chosen_server_without_settings_uses_its_default_image`.
  - `test_unchosen_server_settings_are_not_checked_on_disk`: `agent = "plain"` with
    `[agents.srv.server.volumes]` naming a missing path resolves, and
    `r.server_settings is None`.
  - `test_chosen_server_with_a_missing_volume_stops_the_run`: the same volume with
    `agent = "paired"` raises the `ExceptionGroup`.
  - `test_uninstalled_server_has_no_settings`: `agent = { server = "nope" }`
    resolves with `server_settings is None` (the entry point reports the server).

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/config -q --continue-on-collection-errors`
  Expected: `test_server_settings.py` errors at collection; the new loader tests
  FAIL.

- [ ] **Step 3: Implement.** Validate with filters, not by hand: host paths through
  `f.Unicode | Filepath(...)`, which already expands `~`, resolves and checks
  existence (`is_dir=True` for a volume and `context`, `is_dir=False` for
  `dockerfile`). Turn each filter error into one `ConfigError`. In
  `ConfigLoader.resolve`, after `_resolve_server`, build the settings when
  `server_key in self._servers`, passing that class's `DEFAULT_IMAGE`.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 2: `ManagedContainer`

**Files:**
- Create: `src/paddock/docker/managed.py`
- Modify: `docs/api.rst` only if the strict docs build requires it
- Test: `tests/docker/test_managed.py`

**Interfaces:**
- Produces, in `paddock.docker.managed`:
  ```python
  MANAGED_LABEL = "paddock.managed"
  SPEC_HASH_LABEL = "paddock.spec-hash"
  VOLUMES_LABEL = "paddock.volumes"

  @dataclass(frozen=True)
  class ContainerSpec:
      name: str
      owner: str
      image: str
      command: list[str]
      env: dict[str, str]
      volumes: list[tuple[str, VolumeSpec]]
      container_port: int
      host_port: int | None

      def spec_hash(self) -> str: ...
      def run_argv(self) -> list[str]: ...

  class ContainerState(Enum):
      MISSING = "missing"
      RUNNING = "running"
      STOPPED = "stopped"
      FOREIGN = "foreign"

  @dataclass(frozen=True)
  class ContainerStatus:
      state: ContainerState
      container_id: str | None
      env: dict[str, str]
      labels: dict[str, str]

  class ManagedContainer:
      def __init__(self, spec: ContainerSpec) -> None: ...
      def status(self) -> ContainerStatus: ...
      def start(self) -> None: ...
      def published_port(self) -> int: ...
      @staticmethod
      def volumes_from_labels(labels: dict[str, str]) -> list[tuple[str, VolumeSpec]]: ...
  ```
- `owner` is the label value, e.g. `server:srv`. `name` is both the container's and
  the network's name.
- `run_argv()` is, in this order: `docker run -d --name <name> --network <name>
  --label paddock.managed=<owner> --label paddock.spec-hash=<hash> --label
  paddock.volumes=<json> -p 127.0.0.1:<host_port or empty>:<container_port>`, then
  `-e <NAME>` for each `env` name in sorted order, `-v <host>:<spec>` for each
  volume in order, the image, the command. No value from `env` appears in it.
- `spec_hash()` is a hex SHA-256 over a canonical JSON of image, command, volumes,
  sorted `env` names, `container_port` and `host_port`.
- `status()` runs `docker inspect <name>` once. No such container: `MISSING`. The
  `paddock.managed` label absent or not equal to `owner`: `FOREIGN`. Otherwise
  `RUNNING` or `STOPPED` from `.State.Running`, with the container's ID, its
  environment as a mapping, and its labels.
- `start()` creates the network if it is missing (and raises
  `PaddockEnvironmentError` if a network of that name exists without the label),
  then runs `run_argv()` with `env` merged into the subprocess environment. If
  `docker run` fails because the name is taken, it returns normally: another
  Paddock created it. Any other failure raises `PaddockEnvironmentError` carrying
  Docker's stderr.
- `ManagedContainer` has a method `remove_stopped(container_id: str) -> None` that
  runs `docker rm <container_id>` with no `-f` and ignores failure.
- Error texts, exact:
  - foreign network: `[docker] A network named "<name>" exists that paddock did not
    create; remove or rename it`.
  - `docker run` failure: `[docker] Could not start "<name>": <stderr, stripped>`.

- [ ] **Step 1: Write the failing tests** in `tests/docker/test_managed.py`, with a
  module-level `_stub_docker(mocker, ...)` in the style of `tests/docker/test_pull.py`
  that answers `docker inspect`, `docker network inspect`, `docker network create`,
  `docker run`, `docker rm` and `docker port` from arguments, and records every argv
  and the `env` passed:

  - `test_run_argv_shape`: the full argv for a spec with one env name, one volume
    and no host port, asserted as a list; `-p` is `127.0.0.1::1234`.
  - `test_run_argv_with_a_host_port`: `-p` is `127.0.0.1:4096:1234`.
  - `test_run_argv_never_holds_an_env_value`: with `env={"TOKEN": "s3cr3t"}`,
    `"s3cr3t"` is in no element of `run_argv()`.
  - `test_spec_hash_ignores_env_values_but_not_names`: changing a value keeps the
    hash; adding a name changes it.
  - `test_spec_hash_changes_with_image_command_volumes_and_ports`: one assertion
    per field.
  - `test_status_missing`, `test_status_running`, `test_status_stopped`: from stubbed
    `docker inspect` output.
  - `test_status_foreign_without_the_label` and
    `test_status_foreign_with_another_owner`.
  - `test_status_exposes_env_and_labels`.
  - `test_start_creates_the_network_then_runs`: asserts the order of the recorded
    argvs and that `docker network create` carries the label.
  - `test_start_reuses_an_owned_network`: no `network create`.
  - `test_start_refuses_a_foreign_network`: raises with the exact text; no
    `docker run` is recorded.
  - `test_start_passes_env_values_in_the_environment`: the recorded `env` for
    `docker run` holds `TOKEN=s3cr3t`.
  - `test_start_tolerates_a_name_conflict`: stubbed `docker run` exits 125 with
    stderr containing `is already in use`; `start()` returns.
  - `test_start_reports_other_failures`: stderr `no such image` raises with the
    exact text.
  - `test_remove_stopped_uses_the_id_and_no_force`: the argv is
    `["docker", "rm", "<id>"]`.
  - `test_remove_stopped_ignores_failure`.
  - `test_published_port_parses_docker_port`: stubbed output `127.0.0.1:32768\n`
    gives `32768`.
  - `test_volumes_round_trip_through_labels`: `volumes_from_labels` on the labels
    `run_argv()` sets returns the spec's volumes.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_managed.py -q --continue-on-collection-errors`
  Expected: a collection error (no such module).

- [ ] **Step 3: Implement** the interfaces above. `docker inspect` output is parsed
  as JSON (`--format '{{json .}}'` is not needed; plain `docker inspect` prints a
  JSON array).

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q && uv run make -C docs html SPHINXOPTS="-W --keep-going -E"`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 3: `ServerLauncher`

**Files:**
- Create: `src/paddock/docker/server.py`
- Test: `tests/docker/test_server.py`

**Interfaces:**
- Consumes: `ServerSettings` (Task 1), `ManagedContainer` and friends (Task 2),
  `BaseServer`, `ServerConnection`, `ImageSourceFactory`.
- Produces, in `paddock.docker.server`:
  ```python
  SECRET_ENV = "PADDOCK_SERVER_SECRET"

  @dataclass(frozen=True)
  class LaunchResult:
      connection: ServerConnection
      created: bool
      drifted: bool
      run_argv: list[str] | None

  class ServerLauncher:
      def __init__(self, server: BaseServer, settings: ServerSettings, *, environ: Mapping[str, str], sleep: Callable[[float], None] = time.sleep) -> None: ...
      def launch(self, *, workdir: Path | None, dry_run: bool) -> LaunchResult: ...
  ```
- `workdir` is passed only for a paired client and a server with
  `REQUIRES_WORKDIR_MOUNT`; `None` skips the workdir check. The caller decides.
- `run_argv` is the `docker run` line where the container was, or under `dry_run`
  would be, created; `None` where a running server is used.
- Under `dry_run` with no running server, the connection's `host_url` uses the
  configured port, or the literal `<port>`, and its `secret` is the literal
  `<secret>`.
- All failures raise `PaddockEnvironmentError`. Exact texts, `N` being
  `paddock-server-<key>`:
  - foreign container: `[agent.server] A container named "N" exists that paddock
    did not create; remove or rename it`.
  - no secret on a running server: `[agent.server] Server "<key>" is running
    without a secret paddock can read; to recreate it: docker rm -f N`.
  - not ready: `[agent.server] Server "<key>" was not ready after 30 seconds; see:
    docker logs N`.
  - exited: `[agent.server] Server "<key>" stopped while starting; see: docker logs
    N`.
  - workdir not covered: `[agent.server] Server "<key>" does not have <workdir>
    mounted read-write at the same path; its mounts: <host:spec, comma-separated,
    or none>. Add a mount under [agents.<key>.server.volumes] in your user config,
    then recreate the server: docker rm -f N`.
- The drift warning is the caller's to log (Task 4); `launch` only reports
  `drifted`.

- [ ] **Step 1: Write the failing tests** in `tests/docker/test_server.py`. Use a
  fake `BaseServer` whose `is_ready` returns values from a list the test supplies
  and records each `ServerConnection` it is given; stub `ManagedContainer`'s Docker
  calls with the Task 2 helper pattern; pass `sleep` as a recorder:

  - `test_launch_creates_a_missing_server`: `created is True`, `run_argv` is the
    spec's, the connection's `network` and `container_url` are
    `paddock-server-srv` and `http://paddock-server-srv:<CONTAINER_PORT>`, and
    `host_url` uses the stubbed published port.
  - `test_secret_is_minted_and_exported`: the `docker run` environment holds
    `PADDOCK_SERVER_SECRET` and the server's own variable, both equal to
    `connection.secret`, which is at least 32 characters.
  - `test_secret_never_appears_in_argv`: `connection.secret` is in no element of
    `run_argv`.
  - `test_running_server_is_reused`: no `docker run`; `created is False`;
    `run_argv is None`; the secret is the one in the stubbed `docker inspect`
    environment.
  - `test_running_server_without_a_secret_is_an_error`: exact text.
  - `test_drift_is_reported_not_acted_on`: a running server whose
    `paddock.spec-hash` differs gives `drifted is True`, and no `docker rm` or
    `docker run` is recorded.
  - `test_stopped_server_is_removed_by_id_and_recreated`: the recorded argvs
    include `["docker", "rm", "<observed id>"]` before `docker run`.
  - `test_foreign_container_is_refused`: exact text; nothing is removed or run.
  - `test_name_conflict_is_another_paddocks_server`: `docker run` reports the name
    in use; the second `docker inspect` shows it running with a secret;
    `connection.secret` is that secret, not the one this run minted.
  - `test_readiness_is_polled`: `is_ready` returning `[False, False, True]` sleeps
    twice at 0.5 and succeeds.
  - `test_readiness_times_out`: always `False` raises the not-ready text after 60
    polls.
  - `test_exit_during_start_is_reported`: `docker inspect` showing the container
    stopped during polling raises the exited text, and no `docker rm` is recorded.
  - `test_image_is_prepared_only_on_create`: with `settings.build` set, the image
    source's `refresh` is called once when creating and not at all for a running
    server. Patch `ImageSourceFactory.from_config`.
  - `test_build_args_come_from_the_server`: `from_config` receives
    `agent_build_args=server.get_build_args()`.
  - `test_workdir_under_a_rw_identity_mount_passes`.
  - `test_workdir_outside_every_mount_is_refused`: exact text, listing the mounts.
  - `test_workdir_under_a_readonly_mount_is_refused`.
  - `test_workdir_shadowed_by_a_more_specific_mount_is_refused`: mounts
    `/a` → `/a:rw` and `/other` → `/a/b:rw`, workdir `/a/b/c`.
  - `test_workdir_check_uses_the_servers_own_volumes_too`: a mount from
    `BaseServer.get_volumes()` can shadow, and can cover.
  - `test_running_server_is_judged_by_its_label_not_config`: config now covers the
    workdir, the running container's `paddock.volumes` label does not: refused.
  - `test_no_workdir_skips_the_check`: `workdir=None` with no mounts succeeds.
  - `test_workdir_is_checked_before_anything_is_created`: a refused workdir records
    no `docker run`, no `network create` and no image refresh.
  - `test_dry_run_creates_nothing`: only `docker inspect` is recorded; `run_argv`
    is set; `host_url` ends `:<port>`; `secret == "<secret>"`; `sleep` and
    `is_ready` are never called.
  - `test_dry_run_with_a_configured_port_shows_it`.
  - `test_dry_run_against_a_running_server_reads_it`: the real port and secret.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_server.py -q --continue-on-collection-errors`
  Expected: a collection error (no such module).

- [ ] **Step 3: Implement.** Order inside `launch`: read the container's status;
  refuse a foreign one; build the spec (its `env` needs a secret only when a
  container will be created); run the workdir check against the label's mounts for
  a running server, else the spec's; return early under `dry_run`; remove a stopped
  container; prepare the image; start; re-read status; read the secret and port;
  poll readiness. The mount that covers a path is the one with the longest
  container path that is the path itself or one of its parents, compared as
  `PurePosixPath`s, never by string prefix.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q && uv run make -C docs html SPHINXOPTS="-W --keep-going -E"`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 4: Connect the client

**Files:**
- Modify: `src/paddock/docker/builder.py`, `src/paddock/__main__.py`
- Test: `tests/docker/test_builder.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `LaunchResult` (Task 3), `AgentPairing.is_paired`,
  `ResolvedConfig.server_settings` (Task 1).
- Produces, on `DockerCommandBuilder.__init__`: keyword
  `connection: ServerConnection | None = None`, given only for a paired client.
  With it: one extra `--network <connection.network>` after any configured network;
  `-e <NAME>` for each name in `agent.get_server_env(connection)`, sorted, before
  the image; and the command becomes
  `[*agent.get_command(), *agent.get_server_args(connection), *agent_args]`. A
  replacement command still replaces all of it.
- Produces, on `DockerCommandBuilder`: property `environment -> dict[str, str]`,
  the values behind those `-e` names; `{}` without a connection.
- A configured `network` of `host`, `none`, or starting `container:` with a
  connection raises `PaddockEnvironmentError`: `[network] "<value>" cannot be
  combined with a server's network; agent "<client key>" is paired with server
  "<server key>"`. The builder takes the two keys for this message as keyword
  arguments alongside `connection`.
- `__main__._resolve_pairing` loses its temporary "cannot be started" stop and the
  test for it.

- [ ] **Step 1: Write the failing tests**

  `tests/docker/test_builder.py`, extending `make_agent` to accept
  `server_args` and `server_env`:
  - `test_paired_client_joins_the_servers_network`.
  - `test_paired_client_keeps_its_configured_network_too`: both `--network` flags,
    configured first.
  - `test_server_env_is_passed_by_name_only`: argv has `-e OPENCODE_PASSWORD` and
    no element containing the value; `environment == {"OPENCODE_PASSWORD": <v>}`.
  - `test_server_args_precede_agent_args`: ends
    `["claude", "--server", "http://x", "extra", "cli"]`.
  - `test_replacement_command_drops_server_args`.
  - `test_unpaired_client_is_untouched`: no connection gives today's argv and
    `environment == {}`.
  - One test per refused network value (`host`, `none`, `container:abc`), each
    asserting the exact text.

  `tests/test_main.py`, with fake registries passed through a new keyword on `run`
  (`run(argv, *, agents=agent_registry, servers=server_registry)`, handed on to the
  loader and `_resolve_pairing`) and `ServerLauncher.launch` patched to return a
  `LaunchResult`:
  - `test_paired_run_starts_the_server_then_the_client`: the client's `docker run`
    is given an environment holding the server env value, and its argv the network
    and server args.
  - `test_server_line_is_printed_before_the_client_line`: with
    `LaunchResult.run_argv` set, stdout holds two lines, server first; with it
    `None`, one.
  - `test_secret_is_never_printed_or_logged`: the secret is in neither stdout,
    stderr nor any log record.
  - `test_drift_warns_with_the_recreate_command`: `drifted=True` logs exactly
    `Server "srv" is running with settings that differ from your config; they
    apply when it is recreated: docker rm -f paddock-server-srv`.
  - `test_unpaired_client_beside_a_server_is_not_connected`: the launcher is called
    with `workdir=None`, the builder gets no connection, and the log holds exactly
    `Server: srv (not connected: agent "plain" speaks no server protocol)`.
  - `test_paired_run_logs_the_server_address`: logs `Server: srv (<host_url>)`.
  - `test_workdir_is_passed_only_when_the_server_needs_it`: two cases, the fake
    server's `REQUIRES_WORKDIR_MOUNT` true and false.
  - `test_launch_failure_exits_one_before_paddock_dir`: a
    `PaddockEnvironmentError` from `launch` exits 1 with its text on stderr, and
    `ProjectDirManager.__enter__` is never called (spy, as the unknown-server test
    does).
  - `test_dry_run_launches_with_dry_run`: `launch` receives `dry_run=True` and
    `subprocess.run` is never called.
  - Delete `test_installed_server_cannot_start_yet`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_builder.py tests/test_main.py -q`
  Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `run`, after `_resolve_pairing` and before
  `ProjectDirManager`: where `pairing.server` is set, build a `ServerLauncher` from
  it and `resolved.server_settings` and call `launch`, inside the existing
  `try`/`except PaddockEnvironmentError`. Print the server's `run_argv` with
  `shlex.join` unless `--quiet`. Pass the connection to the builder only when
  `pairing.is_paired`. Run the client with
  `subprocess.run(docker_argv, env={**os.environ, **command_builder.environment})`.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q && uv run make -C docs html SPHINXOPTS="-W --keep-going -E"`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 5: Prove it against real Docker, then retire the plan

**Files:**
- Delete: `docs/superpowers/plans/2026-11-16-managed-server-container.md`

- [ ] **Step 1: Drive the real classes against a real daemon.** Run the
  `e2e-testing` skill's preflight first. No server is bundled, so write a throwaway
  script in the scratchpad (never in the repo) that defines a stand-in `BaseServer`
  whose command is `sleep infinity` on the skill's base image and whose `is_ready`
  returns `True`, then calls `ServerLauncher.launch` directly. Use a key unique to
  the run (`e2e<pid>`), and remove only what the run created, guarding each `docker
  rm`, `docker network rm` and `docker volume rm` against an empty list. Assert,
  each with the script's exit code, not by reading output:
  - a first launch creates the container and network, both labelled, with the port
    published on `127.0.0.1` and the secret in the container's environment;
  - a second launch reuses it, `created is False`, with the same secret;
  - `docker stop` then a launch removes and recreates it with a new container ID;
  - a changed setting (an added volume) reports `drifted is True` and leaves the
    container's ID unchanged;
  - a stand-in whose command is `false` raises the "stopped while starting" error
    and leaves a stopped container whose `docker logs` can be read;
  - a workdir outside the mounts is refused before any container exists;
  - a container of that name created by hand, without the label, is refused and
    still exists afterwards.
  Prove the script can fail: break one assertion's expectation and confirm a
  non-zero exit.

- [ ] **Step 2: Run the whole suite on every supported Python**

  Run: `uv run tox run-parallel` and `uv run pytest --collect-only -q | tail -1`
  Expected: every environment passes; the count is above 450.

- [ ] **Step 3: Delete this plan file** and commit the deletion. Run `git status` to
  catch any related unstaged or untracked files, then use the
  `phx:creative-commits` skill. Push, then open the pull request against
  `develop`. Its description must say that no server is bundled yet, that a
  third-party server registered under `paddock.servers` can now be started, and
  that the user docs land with OpenCode. Have a subagent read the description from
  a scratch file as a reviewer would before posting it.

## Intentional Decisions

*(Populated during review — reviewers must not re-raise these)*

- No user documentation and no bundled server in this plan; both arrive with
  OpenCode in the next pull request.
- `PADDOCK_SERVER_SECRET` is set in the server's environment whatever the server's
  own variable is called, so Paddock can read a secret back without asking the
  server class which name it used.
- Docker access is not wrapped in a client class: `subprocess.run` is stubbed per
  module, as the existing Docker tests do.
- The four minors left from the agent-halves pull request (the `Agent:` log line's
  missing assertion, the wording of the server-only `extra_args` warning, the
  duplicated installed-list helper, `BaseServer`'s bare annotations) stay deferred.
- Real-Docker proof uses a stand-in server driven from a scratch script, not the
  `paddock` command, because no installed server exists for the command to choose.

## Self-Review Checklist

- Does the plan header include a `**Worktree:**` field naming the existing worktree
  and branch?
- Does every commit step remind the agent to run `git status` first?
- Does the plan include an Intentional Decisions section?
- Does the final task delete the plan file?
- Does each Global Constraint have a test in Tasks 1 to 4 or an assertion in Task 5?
- Does each Review Focus line have a named test in the task it cites?
