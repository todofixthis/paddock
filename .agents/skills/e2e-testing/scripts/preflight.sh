#!/usr/bin/env bash
# Prepare the shell for paddock E2E runs. Exits non-zero on anything that
# would make a scenario fail for a reason unrelated to paddock.
set -euo pipefail

DEFAULT_E2E_IMAGE="mcr.microsoft.com/azurelinux/base/core:3.0"
DEFAULT_VENV_DIR=".venv"
E2E_IMAGE="${E2E_IMAGE:-$DEFAULT_E2E_IMAGE}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

# uv reads this as absolute or relative to the project root.
VENV_DIR="${UV_PROJECT_ENVIRONMENT:-$DEFAULT_VENV_DIR}"
case "$VENV_DIR" in
    /*) ;;
    *) VENV_DIR="$REPO_ROOT/$VENV_DIR" ;;
esac
E2E_BIN="$VENV_DIR/bin/paddock"

stray="$(env | grep '^PADDOCK_' || true)"
if [ -n "$stray" ]; then
    echo "❌ PADDOCK_* variables set; paddock treats unknown ones as fatal config errors:"
    echo "$stray"
    exit 1
fi
echo "✅ no PADDOCK_* variables"

if ! docker info >/dev/null 2>&1; then
    if ! command -v dockerd >/dev/null; then
        echo "❌ no docker daemon and no dockerd binary"
        exit 1
    fi
    echo "▶️ starting dockerd"
    nohup dockerd >"${TMPDIR:-/tmp}/dockerd.log" 2>&1 &
    for _ in $(seq 1 30); do
        docker info >/dev/null 2>&1 && break
        sleep 1
    done
    docker info >/dev/null 2>&1 || { echo "❌ dockerd did not come up; see ${TMPDIR:-/tmp}/dockerd.log"; exit 1; }
fi
echo "✅ docker daemon reachable"

if ! docker image inspect "$E2E_IMAGE" >/dev/null 2>&1; then
    echo "⏳ pulling $E2E_IMAGE"
    docker pull -q "$E2E_IMAGE" >/dev/null || {
        echo "❌ cannot pull $E2E_IMAGE (Docker Hub, ECR Public and GHCR blobs are proxy-blocked; mcr.microsoft.com is not)"
        exit 1
    }
fi
echo "✅ image present: $E2E_IMAGE"

if [ ! -x "$E2E_BIN" ]; then
    echo "▶️ syncing venv"
    (cd "$REPO_ROOT" && uv sync --group=dev >/dev/null) || { echo "❌ uv sync failed"; exit 1; }
fi
[ -x "$E2E_BIN" ] || { echo "❌ no paddock binary after sync at $E2E_BIN"; exit 1; }
echo "✅ binary: $E2E_BIN"

command -v script >/dev/null || { echo "❌ 'script' missing; real runs need a pseudo-TTY"; exit 1; }
echo "✅ pseudo-TTY wrapper available"

command -v timeout >/dev/null || { echo "❌ 'timeout' missing; real runs need a time limit"; exit 1; }
echo "✅ timeout available"
