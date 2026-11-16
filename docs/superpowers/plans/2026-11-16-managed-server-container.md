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

Docker facts below were checked against Docker 29.9.2 on 2026-11-16.

- **Identity.** One container per server key, named `paddock-server-<key>`, on a
  bridge network of the same name. Both carry the label
  `paddock.managed=server:<key>`. A container or network of that name without that
  label stops the run. Because the two share a name, always ask Docker for one kind:
  `docker container inspect` and `docker network inspect`, never plain
  `docker inspect`, which returns the network once the container is gone.
- **Lifetime.** `docker run -d`, with no `--rm` and no restart policy. Paddock never
  stops, restarts or force-removes a server. A stopped one is removed by the
  container ID that was observed, without `-f`, and recreated; a failed removal
  means another Paddock got there first and is not an error.
- **Starting is not stopped.** `docker run` creates, then starts. A container whose
  `.State.Status` is `created` with an empty `.State.Error` is starting: it is
  waited for inside the readiness window, and never removed while the window is
  open. A `created` container with an error counts as stopped. One still starting
  when the window closes was abandoned between create and start: it is removed by
  its observed ID without `-f`, which fails harmlessly if it has started since, and
  the run stops saying so.
- **Races.** A concurrent Paddock that loses the race for the container's name, or
  for the network's, re-reads and carries on, waiting for readiness like any other.
- **Mounts.** A server's mounts are, in this order: `BaseServer.get_volumes()`, the
  configured `volumes`, then `BaseServer.get_scratch_volumes()` (named volumes). All
  three go into `-v`, the label and the hash.
- **Run spec in labels.** `paddock.spec-hash` covers the image reference, command,
  mounts, environment variable *names*, container port and requested host port;
  mounts are sorted for it, so reordering config is not drift. `paddock.volumes`
  holds the mounts as JSON, sorted the same way. Drift between the label and config
  warns, prints `docker rm -f paddock-server-<key>`, and uses the running server.
- **Port.** Published on `127.0.0.1` only: the configured `port`, or one Docker
  assigns, read back with `docker port`.
- **Secret.** Minted when the container is created (`secrets.token_urlsafe(32)`),
  set in its environment as `PADDOCK_SERVER_SECRET` beside whatever
  `BaseServer.get_env(secret)` returns, and read back with
  `docker container inspect` on later runs. It reaches Docker as `-e NAME` with the
  value in the subprocess environment, and never appears in a printed or logged
  command, nor in a dataclass `repr`.
- **Readiness.** Every launch polls, a reused server included: up to 60 polls, each
  reading the container's status first and then `BaseServer.is_ready(connection)`,
  sleeping half a second after a poll that is not ready. A container found stopped
  stops the run at once; 60 polls without readiness stop it too. Both point to
  `docker logs paddock-server-<key>` and leave the container, except one still
  starting when the polls run out, which is removed (see above).
- **Image.** Built or pulled under the server's `build` settings only when the
  container is about to be created. Docker's own output is the report; a failure
  stops the run.
- **Settings on disk.** A server's settings are checked on disk only when that
  server is chosen: every volume host path and build path must exist; a `~` first
  segment is expanded. A volume may be a file or a directory, as top-level
  `volumes` may.
- **Workdir check.** Only for a paired client and a server with
  `REQUIRES_WORKDIR_MOUNT`: of all the server's mounts, the one whose container
  path most specifically covers the workdir must be read-write, be a host path and
  not a named volume, and have that container path as its host path. Paths are
  compared as `PurePosixPath`s, never as strings. A running server is judged by its
  `paddock.volumes` label, a server about to be created by its spec.
- **Client network.** A paired client joins the server's network in addition to any
  configured `network`. A configured `host`, `none`, `bridge`, `default` or
  `container:…` cannot be combined with a second network and stops a paired run
  before the server is started. A configured network equal to the server's own is
  passed once. An unpaired client beside a server gets no network, environment or
  arguments from it, and the log says the two are not connected.
- **`--dry-run`** runs every check, the foreign-network one included, prints the
  server's `docker run` line where the container would be created, and creates,
  builds, pulls, removes and mints nothing. Where Docker has not yet assigned a
  host port, the connection's host URL carries `<port>` in its place.
- Everything that consults a registry takes it as a keyword argument. Tests stub
  `subprocess.run` per module, as `tests/docker/test_pull.py` does; no test starts a
  container.
- Commit with `uv run git commit`, from the repo root. NZ English. Flat test
  functions, no lambdas in `parametrize`, Google-style docstrings, comments on the
  line above, implementation in classes.
- The suite collects 450 tests before this plan; the count must rise.

## Review Focus

1. A server that cannot start. A command that runs and exits leaves a stopped
   container: the run stops naming `docker logs`, keeps it, and the next run removes
   it and tries again (Task 3). A missing binary or unknown image fails `docker run`
   itself: the run stops with Docker's own message (Task 2), and any `created`
   leftover is removed next time (Task 3).
2. A user-level volume whose host path does not exist, for a server the run does
   *not* choose: the run is unaffected. For the chosen server it is a config error
   naming the path. Task 1.
3. A workdir under a mount declared `ro`, or shadowed by a more specific mount of
   another host path or of a named volume: the run stops before any client starts.
   Task 3.
4. Two runs starting the same server at once, a stopped container two runs both try
   to remove, and a container one run is still starting: neither run fails, nothing
   mid-start is removed, and both read the one secret. Tasks 2 and 3.
5. The secret: absent from the printed `docker run` lines, from `--dry-run` output
   and from every log record. Tasks 3 and 4.
6. A container named `paddock-server-<key>` that Paddock did not create: the run
   stops and does not remove or adopt it. Tasks 2 and 3.

## File Map

- `src/paddock/config/`: `loader.py`, new `server_settings.py`.
- `src/paddock/docker/`: new `managed.py`, new `server.py`, `builder.py`.
- `src/paddock/__main__.py`.
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
  `settings` is the merged `config["agents"][key]["server"]` table, or `{}` (an
  empty table is dropped by `DropEmpty`). Its `volumes` arrive keyed as written
  with `VolumeSpec` values already cleaned; its `build` paths arrive as strings.
  The returned `volumes` is keyed by the host path with `~` expanded and symlinks
  resolved. `build`, where present, is `{"args": dict, "context": Path | None,
  "dockerfile": Path | None, "policy": str}` with the defaults
  `ConfigLoader._apply_defaults` gives top-level `build`, paths expanded and
  resolved; it is `None` when the table is absent. A `build` with no `dockerfile`
  pulls under its policy, as top-level `build` does (ADR 013).
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
  - `test_a_volume_may_be_a_file`: a real file as the host path is accepted.
  - `test_default_image_fills_a_missing_image`: `{}` with
    `default_image="base"` gives `image == "base"`.
  - `test_configured_image_beats_the_default`.
  - `test_missing_image_without_a_default_is_an_error`: `{}` with
    `default_image=None` raises; the message is exactly
    `[agents.srv.server.image] No image is set, and server "srv" has no default`.
  - `test_missing_volume_path_is_an_error`: a host path that does not exist raises
    with a message starting `[agents.srv.server.volumes./no/such] `.
  - `test_tilde_volume_is_expanded`: with `$HOME` at `tmp_path` and a directory
    `tmp_path / "Dev"`, the key `~/Dev` resolves to
    `str((tmp_path / "Dev").resolve())`.
  - `test_build_paths_must_exist`: a missing `dockerfile` raises at
    `[agents.srv.server.build.dockerfile]`; a missing `context` at
    `[agents.srv.server.build.context]`.
  - `test_build_defaults_match_the_top_level_build`: `{"image": "i", "build":
    {"dockerfile": <real file>}}` gives `build == {"args": {}, "context": None,
    "dockerfile": <resolved Path>, "policy": "if-missing"}`.
  - `test_build_without_a_dockerfile_is_kept`: `{"image": "i", "build": {"policy":
    "daily"}}` gives `build["dockerfile"] is None` and `build["policy"] == "daily"`.
  - `test_port_is_carried`: `{"image": "i", "port": 4096}` gives `port == 4096`.
  - `test_every_problem_is_reported`: a missing volume and a missing dockerfile
    together raise two `ConfigError`s.

  `tests/config/test_loader.py`. Its `_resolve_agent_config` helper gains a fake
  `servers` registry holding a new fake server `srv` with
  `DEFAULT_IMAGE = "srv-default"`; the `paired` client's `DEFAULT_SERVER` is
  already `"srv"`:
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
  existence (`is_dir=True` for `context`, `is_dir=False` for `dockerfile`, neither
  for a volume). Turn each filter error into one `ConfigError`. In
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
      env: dict[str, str] = field(repr=False)
      volumes: list[tuple[str, VolumeSpec]]
      container_port: int
      host_port: int | None

      def spec_hash(self) -> str: ...
      def run_argv(self) -> list[str]: ...

  class ContainerState(Enum):
      MISSING = "missing"
      STARTING = "starting"
      RUNNING = "running"
      STOPPED = "stopped"
      FOREIGN = "foreign"

  @dataclass(frozen=True)
  class ContainerStatus:
      state: ContainerState
      container_id: str | None
      env: dict[str, str] = field(repr=False)
      labels: dict[str, str]

  class ManagedContainer:
      def __init__(self, spec: ContainerSpec) -> None: ...
      def status(self) -> ContainerStatus: ...
      def check_network(self) -> None: ...
      def start(self) -> bool: ...
      def remove_stopped(self, container_id: str) -> None: ...
      def published_port(self) -> int | None: ...
      @staticmethod
      def volumes_from_labels(labels: dict[str, str]) -> list[tuple[str, VolumeSpec]]: ...
  ```
- `owner` is the label value, e.g. `server:srv`. `name` is both the container's and
  the network's name. A volume's first element is a host path or a volume name.
- `run_argv()` is, in this order: `docker run -d --name <name> --network <name>
  --label paddock.managed=<owner> --label paddock.spec-hash=<hash> --label
  paddock.volumes=<json> -p 127.0.0.1:<host_port or empty>:<container_port>`, then
  `-e <NAME>` for each `env` name in sorted order, `-v <host or name>:<spec>` for
  each volume in the spec's order, the image, the command. No value from `env`
  appears in it.
- `spec_hash()` is a hex SHA-256 over a canonical JSON of image, command, volumes
  (sorted), sorted `env` names, `container_port` and `host_port`. The
  `paddock.volumes` label holds the volumes sorted the same way.
- `status()` runs `docker container inspect <name>` once. Exit 1: `MISSING`. The
  `paddock.managed` label absent or not equal to `owner`: `FOREIGN`.
  `.State.Running` true: `RUNNING`. `.State.Status == "created"` with an empty
  `.State.Error`: `STARTING`. Anything else: `STOPPED`. The status carries the
  container's ID, its labels, and its environment parsed with
  `entry.partition("=")`, an entry with no `=` mapping to `""`.
- `check_network()` reads `docker network inspect <name>` and raises
  `PaddockEnvironmentError` if a network of that name exists without the label. It
  creates nothing.
- `start()` calls `check_network()`, creates the network if it is missing, then
  runs `run_argv()` with `env` merged over `os.environ` for that subprocess. It
  returns `True` when it created the container. Losing a race is not an error: if
  `docker network create` fails and the network now exists with the label, carry
  on; if `docker run` fails with `Conflict. The container name` in its stderr,
  return `False`. A port conflict also says "already in use" and must not match. Any other `docker run` failure raises
  `PaddockEnvironmentError` carrying the first non-empty line of Docker's stderr.
- `remove_stopped()` runs `docker rm <container_id>` with no `-f` and ignores
  failure.
- `published_port()` parses `docker port <name> <container_port>/tcp` and returns
  `None` when Docker reports no published port, as it does for a stopped container.
- Error texts, exact:
  - foreign network: `[docker] A network named "<name>" exists that paddock did not
    create; remove or rename it`.
  - `docker run` failure: `[docker] Could not start "<name>": <first line>`.

- [ ] **Step 1: Write the failing tests** in `tests/docker/test_managed.py`, with a
  module-level `_stub_docker(mocker, ...)` in the style of `tests/docker/test_pull.py`
  that answers `docker container inspect`, `docker network inspect`,
  `docker network create`, `docker run`, `docker rm` and `docker port` from
  arguments, and records every argv and the `env` passed:

  - `test_run_argv_shape`: the full argv for a spec with one env name, one host
    volume, one named volume and no host port, asserted as a list; `-p` is
    `127.0.0.1::1234`.
  - `test_run_argv_with_a_host_port`: `-p` is `127.0.0.1:4096:1234`.
  - `test_run_argv_never_holds_an_env_value`: with `env={"TOKEN": "s3cr3t"}`,
    `"s3cr3t"` is in no element of `run_argv()`, and not in `repr(spec)`.
  - `test_spec_hash_ignores_env_values_but_not_names`: changing a value keeps the
    hash; adding a name changes it.
  - `test_spec_hash_changes_with_image_command_volumes_and_ports`: one assertion
    per field.
  - `test_spec_hash_ignores_volume_order`.
  - `test_status_missing`, `test_status_running`, `test_status_stopped`: from stubbed
    `docker container inspect` output.
  - `test_status_created_is_starting`: `Status: created`, `Error: ""`.
  - `test_status_created_with_an_error_is_stopped`.
  - `test_status_foreign_without_the_label` and
    `test_status_foreign_with_another_owner`.
  - `test_status_exposes_env_and_labels`: the environment includes an entry with no
    `=`, which maps to `""`; `repr(status)` does not contain a value from it.
  - `test_status_asks_for_a_container_not_any_object`: the recorded argv begins
    `["docker", "container", "inspect"]`.
  - `test_start_creates_the_network_then_runs`: asserts the order of the recorded
    argvs and that `docker network create` carries the label.
  - `test_start_reuses_an_owned_network`: no `network create`.
  - `test_start_refuses_a_foreign_network`: raises with the exact text; no
    `docker run` is recorded.
  - `test_check_network_creates_nothing`: only `docker network inspect` is
    recorded, for a missing network and for an owned one.
  - `test_start_tolerates_a_network_create_race`: `network create` exits 1, the
    second inspect shows the labelled network, and `docker run` is recorded.
  - `test_start_passes_env_values_in_the_environment`: the recorded `env` for
    `docker run` holds `TOKEN=s3cr3t`.
  - `test_start_tolerates_a_name_conflict`: stubbed `docker run` exits 125 with
    stderr `docker: Error response from daemon: Conflict. The container name
    "/n" is already in use by container "abc".`; `start()` returns `False`.
  - `test_start_returns_true_when_it_created_the_container`.
  - `test_a_port_conflict_is_not_a_name_conflict`: stderr `docker: Error response
    from daemon: failed to bind host port for 127.0.0.1:4096: address already in
    use` raises the could-not-start text.
  - `test_start_reports_other_failures`: stderr of two lines, `docker: Error
    response from daemon: no such image` then `Run 'docker run --help' for more
    information`, raises with the exact text ending in the first line only.
  - `test_remove_stopped_uses_the_id_and_no_force`: the argv is
    `["docker", "rm", "<id>"]`.
  - `test_remove_stopped_ignores_failure`.
  - `test_published_port_parses_docker_port`: stubbed output `127.0.0.1:32768\n`
    gives `32768`.
  - `test_published_port_is_none_when_unpublished`: `docker port` exits 1.
  - `test_volumes_round_trip_through_labels`: `volumes_from_labels` on the labels
    `run_argv()` sets returns the spec's volumes, sorted.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_managed.py -q --continue-on-collection-errors`
  Expected: a collection error (no such module).

- [ ] **Step 3: Implement** the interfaces above. `docker container inspect` and
  `docker network inspect` print a JSON array; parse it, do not use `--format`.

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
- `run_argv` is the `docker run` line where this run created the container, or
  under `dry_run` would; `None` otherwise.
- `connection.host_url` is `http://127.0.0.1:<published port>` and
  `connection.container_url` is `http://paddock-server-<key>:<CONTAINER_PORT>`.
  Under `dry_run` with no running server, `host_url` uses the configured port, or
  the literal `<port>`, and `secret` is the literal `<secret>`.
- Change `ServerConnection.secret` in `paddock.agents.servers` to
  `field(repr=False)`.
- All failures raise `PaddockEnvironmentError`. Exact texts, `N` being
  `paddock-server-<key>`:
  - foreign container: `[agent.server] A container named "N" exists that paddock
    did not create; remove or rename it`.
  - no secret on a running server: `[agent.server] Server "<key>" is running
    without a secret paddock can read; to recreate it: docker rm -f N`.
  - not ready: `[agent.server] Server "<key>" was not ready after 30 seconds; see:
    docker logs N`.
  - stopped: `[agent.server] Server "<key>" stopped while starting; see: docker logs
    N`.
  - never started: `[agent.server] Server "<key>" was created but never started; it
    has been removed, so run again`.
  - image: `[agent.server] Could not build or pull the image for server "<key>":
    docker exited <status>`.
  - workdir not covered: `[agent.server] Server "<key>" does not have <workdir>
    mounted read-write at the same path; its mounts: <host or name:spec,
    comma-separated, or none>. Add a mount under [agents.<key>.server.volumes] in
    your user config`, followed by `, then recreate the server: docker rm -f N` only
    where the server is running or starting. The mounts are listed sorted.
- The drift warning is the caller's to log (Task 4); `launch` only reports
  `drifted`.

- [ ] **Step 1: Write the failing tests** in `tests/docker/test_server.py`. Use a
  fake `BaseServer` whose `is_ready` returns values from a list the test supplies
  and records each `ServerConnection` it is given; stub Docker with the Task 2
  helper pattern, able to change the answer to `docker container inspect` between
  calls; pass `sleep` as a recorder:

  - `test_launch_creates_a_missing_server`: `created is True`, `run_argv` is the
    spec's, the connection's `network` and `container_url` are
    `paddock-server-srv` and `http://paddock-server-srv:<CONTAINER_PORT>`, and
    `host_url` is `http://127.0.0.1:<stubbed port>`.
  - `test_mounts_are_the_servers_then_configured_then_scratch`: asserted on the
    `-v` flags of `run_argv`, in that order.
  - `test_secret_is_minted_and_exported`: the `docker run` environment holds
    `PADDOCK_SERVER_SECRET` and the server's own variable, both equal to
    `connection.secret`, which is at least 32 characters. The stub serves the
    created container's `Config.Env` from the environment `docker run` was given.
  - `test_secret_never_appears_in_argv_logs_or_repr`: `connection.secret` is in no
    element of `run_argv`, in no `caplog` record at any level, and not in
    `repr(result)`.
  - `test_running_server_is_reused`: no `docker run`; `created is False`;
    `run_argv is None`; `drifted is False`; the secret is the one in the stubbed
    inspect environment; `is_ready` is called. Take the stub's `paddock.spec-hash`
    from the `run_argv` of a creating launch with the same fixtures, not from a
    spec rebuilt by hand.
  - `test_running_server_without_a_secret_is_an_error`: exact text.
  - `test_drift_is_reported_not_acted_on`: a running server whose
    `paddock.spec-hash` differs gives `drifted is True`, and no `docker rm` or
    `docker run` is recorded.
  - `test_stopped_server_is_removed_by_id_and_recreated`: the recorded argvs
    include `["docker", "rm", "<observed id>"]` before `docker run`.
  - `test_created_leftover_with_an_error_is_removed_and_recreated`.
  - `test_a_starting_container_is_waited_for_not_removed`: inspect answers
    `created` twice, then running; no `docker rm` and no `docker run` is recorded,
    and the launch succeeds.
  - `test_a_container_stuck_starting_is_removed`: always `created` with an empty
    error raises the never-started text after 60 polls, `is_ready` is never called,
    and `["docker", "rm", "<observed id>"]` is recorded.
  - `test_foreign_container_is_refused`: exact text; nothing is removed or run.
  - `test_name_lost_to_a_foreign_container_is_refused`: `docker run` reports the
    name in use and the next inspect shows a container without the label; the
    foreign-container text is raised.
  - `test_name_conflict_is_another_paddocks_server`: `docker run` reports the name
    in use; the next inspect shows it running with a secret; `connection.secret`
    is that secret, not the one this run minted; `created is False` and
    `run_argv is None`.
  - `test_readiness_is_polled`: `is_ready` returning `[False, False, True]` sleeps
    twice at 0.5 and succeeds.
  - `test_readiness_times_out`: always `False` raises the not-ready text after 60
    calls to `is_ready` and 60 sleeps; no `docker rm` is recorded.
  - `test_exit_during_start_is_reported`: inspect showing the container stopped
    during polling raises the stopped text before `is_ready` is called again, and
    no `docker rm` is recorded.
  - `test_unpublished_port_is_polled_again`: `docker port` reporting nothing once,
    then a port, succeeds after one sleep.
  - `test_a_container_that_vanishes_while_polling_is_reported`: inspect answering
    missing during the loop raises the stopped text.
  - `test_stopped_before_the_port_is_read_is_reported`: `docker port` reporting no
    port with the container stopped raises the stopped text.
  - `test_image_is_prepared_only_on_create`: with `settings.build` set, the image
    source's `refresh` is called once when creating and not at all for a running
    server. Patch `ImageSourceFactory.from_config`.
  - `test_image_failure_is_reported`: `refresh` raising
    `subprocess.CalledProcessError(3, ...)` raises the image text with `3`, and no
    `docker run` is recorded.
  - `test_build_args_come_from_the_server`: `from_config` receives
    `agent_build_args=server.get_build_args()`.
  - `test_workdir_under_a_rw_identity_mount_passes`.
  - `test_workdir_equal_to_a_mount_point_passes`.
  - `test_workdir_outside_every_mount_is_refused`: exact text, listing the mounts,
    without the recreate clause when no container is running and with it when one is.
  - `test_workdir_under_a_readonly_mount_is_refused`.
  - `test_workdir_shadowed_by_a_more_specific_mount_is_refused`: mounts
    `/a` → `/a:rw` and `/other` → `/a/b:rw`, workdir `/a/b/c`.
  - `test_workdir_shadowed_by_a_named_volume_is_refused`: a scratch volume at
    `/a/b`.
  - `test_sibling_prefix_does_not_cover`: mount `/a`, workdir `/ab/c`.
  - `test_trailing_slash_on_a_container_path_still_matches`: a server volume
    `VolumeSpec("/a/", "rw")` from host `/a` covers `/a/b`.
  - `test_workdir_check_uses_the_servers_own_volumes_too`: a mount from
    `BaseServer.get_volumes()` can shadow, and can cover.
  - `test_running_server_is_judged_by_its_label_not_config`: config now covers the
    workdir, the running container's `paddock.volumes` label does not: refused.
  - `test_no_workdir_skips_the_check`: `workdir=None` with no mounts succeeds.
  - `test_workdir_is_checked_before_anything_is_created`: a refused workdir records
    no `docker run`, no `network create` and no image refresh.
  - `test_dry_run_creates_nothing`: only `docker container inspect` and
    `docker network inspect` are recorded; `run_argv` is set; `host_url` ends
    `:<port>`; `secret == "<secret>"`; `drifted is False`; `sleep`, `is_ready` and the image source's
    `refresh` are never called.
  - `test_dry_run_refuses_a_foreign_network`.
  - `test_dry_run_with_a_configured_port_shows_it`.
  - `test_dry_run_against_a_running_server_reads_it`: the real port and secret,
    `run_argv is None`, and neither `is_ready` nor `sleep` is called.
  - `test_dry_run_against_a_stopped_server_removes_nothing`: with a stopped
    container whose `paddock.spec-hash` differs, `run_argv` is set,
    `drifted is False` and no `docker rm` is recorded.
  - `test_dry_run_against_a_starting_server_uses_placeholders`: `run_argv is None`,
    `secret == "<secret>"`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_server.py -q --continue-on-collection-errors`
  Expected: a collection error (no such module).

- [ ] **Step 3: Implement.** Order inside `launch`:

  1. Read the container's status; refuse a foreign one.
  2. Build the spec. Its environment variable *names* must be the same whether or
     not a container will be created, or every reuse would read as drift: use the
     minted secret when the container is missing or stopped and this is not a dry
     run, and `get_env("<secret>")` plus `SECRET_ENV` otherwise.
  3. Run the workdir check, against the label's mounts where the container is
     running or starting, else the spec's.
  4. Check the network.
  5. Under `dry_run`, return now: a running server has its secret read once (none
     raises the no-secret text) and its published port read once (none falls back
     to the configured port, or `<port>`); a starting one, or none, gets the
     placeholders; `run_argv` is
     set only where the container is missing or stopped. Nothing is removed.
  6. Where the container is missing or stopped: remove a stopped one, prepare the
     image where `settings.build` is set, then start. Running and starting
     containers skip all three.
  7. One loop of up to 60 polls does the waiting for every path. Each poll reads
     the status. Foreign raises the foreign-container text; stopped or missing
     raises the stopped text; starting sleeps. Running has its secret read (none
     raises) and its port read (none sleeps, and the next poll re-reads the
     status), then `is_ready` is called, returning on `True` and sleeping
     otherwise.
  8. When the polls run out: if the last status was starting, remove it by its
     observed ID and raise the never-started text; otherwise raise the not-ready
     text.

  `created` is `True` only where this run's `start()` created the container.
  `drifted` is computed only where the result uses a container this run did not
  create (running or starting), from the labels of the status read by the poll, or
  the dry-run read, that returns; it is `False` wherever `run_argv` is set or no
  container exists. The mount that covers
  a path is the one with the longest container path that is the path itself or one
  of its parents. Do not assert exact counts of inspect calls in the tests:
  `start()` checks the network again.

- [ ] **Step 4: Run the checks**

  Run: `uv run mypy src/ tests/ && uv run ruff check && uv run pytest -q && uv run make -C docs html SPHINXOPTS="-W --keep-going -E"`
  Expected: all pass.

- [ ] **Step 5: Commit**

  Run `git status` to catch any related unstaged or untracked files (e.g. lock files
  after dependency changes), then use the `phx:creative-commits` skill, then
  `git push`.

### Task 4: Connect the client

**Files:**
- Modify: `src/paddock/docker/builder.py`, `src/paddock/__main__.py`,
  `docs/adr/019-run-one-shared-container-per-agent-server.md`
- Test: `tests/docker/test_builder.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `LaunchResult` (Task 3), `AgentPairing.is_paired`,
  `ResolvedConfig.server_settings` (Task 1).
- Produces, on `DockerCommandBuilder.__init__`: keyword
  `connection: ServerConnection | None = None`, given only for a paired client.
  With it: `--network <connection.network>` after any configured network, omitted
  when the two are equal; `-e <NAME>` for each name in
  `agent.get_server_env(connection)`, sorted, before the image; and the command
  becomes `[*agent.get_command(), *agent.get_server_args(connection),
  *agent_args]`. A replacement command still replaces all of it.
- Produces, on `DockerCommandBuilder`: property `environment -> dict[str, str]`,
  the values behind those `-e` names; `{}` without a connection.
- Produces, on `DockerCommandBuilder`:
  `@staticmethod check_paired_network(network: str | None, *, agent_key: str, server_key: str) -> None`,
  which raises `PaddockEnvironmentError` for `host`, `none`, `bridge`, `default` or
  a value starting `container:`, with exactly: `[network] "<value>" cannot be
  combined with a server's network; agent "<agent_key>" is paired with server
  "<server_key>"`.
- Produces: `run(argv: list[str] | None = None, *, agents=agent_registry,
  servers=server_registry)`, handing both on to the loader and `_resolve_pairing`.
- `__main__._resolve_pairing` loses its temporary "cannot be started" stop.

- [ ] **Step 1: Write the failing tests**

  `tests/docker/test_builder.py`, extending `make_agent` to accept
  `server_args` and `server_env`:
  - `test_paired_client_joins_the_servers_network`.
  - `test_paired_client_keeps_its_configured_network_too`: both `--network` flags,
    configured first.
  - `test_configured_network_equal_to_the_servers_is_passed_once`.
  - `test_server_env_is_passed_by_name_only`: argv has `-e OPENCODE_PASSWORD` and
    no element containing the value; `environment == {"OPENCODE_PASSWORD": <v>}`.
  - `test_server_args_precede_agent_args`: ends
    `["claude", "--server", "http://x", "extra", "cli"]`.
  - `test_replacement_command_drops_server_args`.
  - `test_unpaired_client_is_untouched`: no connection gives today's argv and
    `environment == {}`.
  - `test_paired_network_check_refuses_uncombinable_networks`, parametrised over
    `host`, `none`, `bridge`, `default` and `container:abc`, asserting the exact
    text.
  - `test_paired_network_check_allows_a_user_network_or_none`.

  `tests/test_main.py`, with fake registries passed to `run`,
  `ServerLauncher.launch` patched to return a `LaunchResult`, and
  `DockerCommandBuilder._container_name_available` patched as the existing dry-run
  tests do:
  - `test_paired_run_starts_the_server_then_the_client`: the client's
    `subprocess.run` is given an environment holding the server env value, and its
    argv the network and server args.
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
  - `test_uncombinable_network_stops_before_the_server_starts`: a paired run with
    `network = "host"` exits 1 with the text above, and `launch` is never called.
  - `test_launch_failure_exits_one_before_paddock_dir`: a
    `PaddockEnvironmentError` from `launch` exits 1 with its text on stderr, and
    `ProjectDirManager.__enter__` is never called (spy, as the unknown-server test
    does).
  - `test_dry_run_launches_with_dry_run`: `launch` receives `dry_run=True` and the
    client's `docker run` is never executed.
  - Delete `test_installed_server_cannot_start_yet`.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `uv run pytest tests/docker/test_builder.py tests/test_main.py -q`
  Expected: the new tests FAIL.

- [ ] **Step 3: Implement.** In `run`, after `_resolve_pairing` and before
  `ProjectDirManager`, inside the existing `try`/`except PaddockEnvironmentError`:
  where the pairing is paired, call `check_paired_network`; where `pairing.server`
  is set, build a `ServerLauncher` from it and `resolved.server_settings` (narrow
  the `None` for mypy) and call `launch`. Print the server's `run_argv` with
  `shlex.join` unless `--quiet`. Pass the connection to the builder only when
  `pairing.is_paired`. Run the client with
  `subprocess.run(docker_argv, env={**os.environ, **command_builder.environment})`.
  In ADR 019's Network bullet, change "(`host`, `none`, `container:`)" to
  "(`host`, `none`, `bridge`, `default`, `container:`)" and regenerate nothing: the
  index does not carry the body.

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
  the run (`e2e<pid>`), stop containers with `docker stop -t 0`, and remove only
  what the run created, guarding each `docker rm`, `docker network rm` and
  `docker volume rm` against an empty list. Assert, each through the script's exit
  code, not by reading output:
  - a first launch creates the container and network, both labelled, with the port
    published on `127.0.0.1` and the secret in the container's environment;
  - a second launch reuses it, `created is False`, with the same secret;
  - after `docker rm -f` of the container alone, leaving its network, a launch
    recreates it (the case plain `docker inspect` would get wrong);
  - `docker stop -t 0` then a launch removes and recreates it with a new ID;
  - a changed setting (an added volume) reports `drifted is True` and leaves the
    container's ID unchanged;
  - a stand-in whose command is `false` and whose `is_ready` returns `False` raises
    the "stopped while starting" error and leaves a stopped container whose
    `docker logs` can be read;
  - a stand-in whose command is a binary the image lacks raises the "Could not
    start" error;
  - a workdir outside the mounts is refused before any container exists;
  - a container of that name created by hand, without the label, is refused and
    still exists afterwards;
  - two launches started at once from two processes both succeed with one
    container and the same secret.
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
- Points ADR 019 leaves open, decided here: the label names and the `server:<key>`
  value; the network sharing the container's name; the spec hash covering the image
  reference, not its ID, and not `build`; volume host paths being symlink-resolved
  before the identity comparison; readiness as 60 polls half a second apart, for a
  reused server too; the mount order.
- The `paddock.volumes` label is bounded by the kernel's 128 KiB limit on one
  argument. No server's mounts approach it, so nothing guards against it.
- Two `--network` flags need a recent Docker (checked on 29.9.2). The design's
  fallback of `docker network connect` is dropped: it does not fit a foreground
  `docker run --rm -it`. An older Docker fails with its own message.
- With no `build` settings and a missing image, `docker run -d` pulls quietly; a
  first run can pause without output. Left as it is.
- The server's `docker run` line is printed after `launch` returns, so a failed
  start shows the error and not the line.
- A container path containing `..`, or two mounts at one container path, is left
  for Docker to reject.

## Self-Review Checklist

- Does the plan header include a `**Worktree:**` field naming the existing worktree
  and branch?
- Does every commit step remind the agent to run `git status` first?
- Does the plan include an Intentional Decisions section?
- Does the final task delete the plan file?
- Does each Global Constraint have a test in Tasks 1 to 4 or an assertion in Task 5?
- Does each Review Focus line have a named test in the task it cites?
