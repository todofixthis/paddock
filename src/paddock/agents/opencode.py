import base64
import http.client
import urllib.request

from paddock.agents.servers import BaseServer, Secret, ServerConnection
from paddock.config.filters import VolumeSpec

# The protocol name that pairs OpenCode's client with its server.
OPENCODE_PROTOCOL = "opencode"

# OpenCode reads its password from this variable on both sides, and takes
# this fixed username with it over HTTP Basic.
OPENCODE_PASSWORD_ENV = "OPENCODE_PASSWORD"
OPENCODE_USERNAME = "opencode"

# Stops a client or server replacing the version the image pins.
OPENCODE_FIXED_ENV = {"OPENCODE_DISABLE_AUTOUPDATE": "1"}


class OpenCodeServer(BaseServer):
    """OpenCode's server, which runs every tool the agent uses (ADR 021)."""

    SERVER_KEY = "opencode"
    PROTOCOL = OPENCODE_PROTOCOL
    CONTAINER_PORT = 4096
    REQUIRES_WORKDIR_MOUNT = True

    # Seconds one readiness probe may take before it counts as not ready.
    READY_TIMEOUT = 2.0

    # The probe goes to loopback, which a proxy from the environment would
    # never reach: with one set, every probe would read as not ready.
    _OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get_command(self) -> list[str]:
        """Listen on every interface, so clients on the network reach it."""
        port = str(self.CONTAINER_PORT)
        return ["opencode", "serve", "--hostname", "0.0.0.0", "--port", port]

    def get_scratch_volumes(self) -> dict[str, VolumeSpec]:
        """Keep the database and state out of the container (ADR 021).

        Not the host's OpenCode directories by default: a host
        ``opencode`` would open the same database beside this server. A
        user shares one by mounting it at the same path.
        """
        return {
            "paddock-server-opencode-data": VolumeSpec(
                "/root/.local/share/opencode", "rw"
            ),
            "paddock-server-opencode-state": VolumeSpec(
                "/root/.local/state/opencode", "rw"
            ),
        }

    def get_build_args(self) -> dict[str, str]:
        return {"AGENT": "opencode"}

    def get_env(self, secret: str) -> dict[str, str | Secret]:
        """Always set a password: without one OpenCode mints its own."""
        return {**OPENCODE_FIXED_ENV, OPENCODE_PASSWORD_ENV: secret}

    def is_ready(self, connection: ServerConnection) -> bool:
        """Report whether ``GET /api/info`` answers 200 with the password.

        OpenCode answers 503 while starting and 401 without the password.
        """
        credentials = f"{OPENCODE_USERNAME}:{connection.secret}".encode()
        token = base64.b64encode(credentials).decode()
        request = urllib.request.Request(
            f"{connection.host_url}/api/info",
            headers={"Authorization": f"Basic {token}"},
        )
        try:
            with self._OPENER.open(request, timeout=self.READY_TIMEOUT) as reply:
                return bool(reply.status == 200)
        except (OSError, http.client.HTTPException):
            return False
