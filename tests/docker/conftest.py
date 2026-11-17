import json
import subprocess

import pytest


class FakeDocker:
    """A scriptable stand-in for the ``docker`` CLI behind ``subprocess.run``.

    It holds one container and one network, as one managed name has. A
    successful ``docker run`` creates a running container from its argv and
    environment, so a test can read back what the code under test wrote.
    """

    def __init__(self, mocker, module: str = "paddock.docker.managed") -> None:
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str] | None] = []
        self.container: dict | None = None
        self.network: dict | None = None
        # Served by successive ``docker container inspect`` calls, ahead of
        # ``container``; the last entry then becomes ``container``.
        self.inspect_script: list[dict | None] = []
        # Served by successive ``docker port`` calls, ahead of ``port``.
        self.port_script: list[str | None] = []
        self.port: str | None = "127.0.0.1:32768"
        self.run_returncode = 0
        self.run_stderr = ""
        # The container another process is taken to have created when this
        # one's ``docker run`` fails.
        self.container_after_failed_run: dict | None = None
        self.network_create_returncode = 0
        # The network another process is taken to have created when this
        # one's ``docker network create`` fails.
        self.network_after_failed_create: dict | None = None
        self.rm_returncode: int | None = None
        self._created = 0
        mocker.patch(f"{module}.subprocess.run", side_effect=self._run)

    def ran(self, *prefix: str) -> list[list[str]]:
        """Every recorded argv starting with ``prefix``."""
        return [c for c in self.calls if c[: len(prefix)] == list(prefix)]

    def env_of(self, *prefix: str) -> dict[str, str]:
        """The environment the first call starting with ``prefix`` was given."""
        for call, env in zip(self.calls, self.envs):
            if call[: len(prefix)] == list(prefix):
                assert env is not None
                return env
        raise AssertionError(f"no call starting {prefix}")

    def _run(self, argv, **kwargs):
        self.calls.append(list(argv))
        self.envs.append(kwargs.get("env"))
        handler = {
            ("container", "inspect"): self._container_inspect,
            ("network", "inspect"): self._network_inspect,
            ("network", "create"): self._network_create,
        }.get(tuple(argv[1:3])) or {
            "run": self._docker_run,
            "rm": self._rm,
            "port": self._port,
        }[
            argv[1]
        ]
        code, out, err = handler(argv, kwargs.get("env") or {})
        return subprocess.CompletedProcess(argv, code, stdout=out, stderr=err)

    def _container_inspect(self, argv, env):
        if self.inspect_script:
            self.container = self.inspect_script.pop(0)
        if self.container is None:
            return 1, "[]\n", "Error response from daemon: No such container\n"
        return 0, json.dumps([self.container]), ""

    def _network_inspect(self, argv, env):
        if self.network is None:
            return 1, "[]\n", "Error response from daemon: network not found\n"
        return 0, json.dumps([self.network]), ""

    def _network_create(self, argv, env):
        if self.network_create_returncode:
            self.network = self.network_after_failed_create
            return self.network_create_returncode, "", "Error: network exists\n"
        labels = dict(a.split("=", 1) for a in self._values(argv, "--label"))
        self.network = {"Labels": labels}
        return 0, "netid\n", ""

    def _docker_run(self, argv, env):
        if self.run_returncode:
            self.container = self.container_after_failed_run
            return self.run_returncode, "", self.run_stderr
        self._created += 1
        labels = dict(a.split("=", 1) for a in self._values(argv, "--label"))
        owner = labels.pop("paddock.managed", None)
        self.container = self.container_entry(
            owner=owner,
            env=[
                flag if "=" in flag else f"{flag}={env[flag]}"
                for flag in self._values(argv, "-e")
            ],
            labels=labels,
            container_id=f"created{self._created}",
        )
        return 0, f"created{self._created}\n", ""

    def _rm(self, argv, env):
        if self.rm_returncode is not None:
            return self.rm_returncode, "", "Error\n"
        if self.container is None or self.container["Id"] != argv[-1]:
            return 1, "", "Error response from daemon: No such container\n"
        if self.container["State"]["Running"]:
            return 1, "", "Error response from daemon: container is running\n"
        self.container = None
        return 0, argv[-1] + "\n", ""

    def _port(self, argv, env):
        port = self.port_script.pop(0) if self.port_script else self.port
        running = self.container is not None and self.container["State"]["Running"]
        if port is None or not running:
            return 1, "", "Error: no public port\n"
        return 0, port + "\n", ""

    @staticmethod
    def _values(argv: list[str], flag: str) -> list[str]:
        """Every value given to ``flag`` in ``argv``."""
        return [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == flag]

    @staticmethod
    def container_entry(
        *,
        owner: str | None = "server:srv",
        status: str = "running",
        error: str = "",
        env: list[str] | None = None,
        labels: dict[str, str] | None = None,
        container_id: str = "abc123",
    ) -> dict:
        """One element of ``docker container inspect``'s JSON array.

        Args:
            owner: The ``paddock.managed`` label's value, or ``None`` for none.
            status: ``.State.Status``; ``running`` also sets ``.State.Running``.
            error: ``.State.Error``.
            env: ``.Config.Env``.
            labels: Further labels.
            container_id: ``.Id``.
        """
        all_labels = dict(labels or {})
        if owner is not None:
            all_labels["paddock.managed"] = owner
        return {
            "Config": {"Env": list(env or []), "Labels": all_labels},
            "Id": container_id,
            "State": {"Error": error, "Running": status == "running", "Status": status},
        }

    @staticmethod
    def network_entry(owner: str | None = "server:srv") -> dict:
        """One element of ``docker network inspect``'s JSON array."""
        return {"Labels": {} if owner is None else {"paddock.managed": owner}}


@pytest.fixture
def docker(mocker) -> FakeDocker:
    """A fake ``docker`` CLI with no container and no network."""
    return FakeDocker(mocker)
