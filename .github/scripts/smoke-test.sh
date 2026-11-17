#!/usr/bin/env bash
# Smoke test for images/Dockerfile. Runs inside the built image, with the
# Dockerfile mounted beside it, and checks each install runs and reports the
# version its ARG default names. Most of those versions a successful build
# already guarantees; the Node.js major is the one that can differ, since
# NodeSource missing a release leaves Ubuntu's own nodejs (ADR 016).
#
# Usage: smoke-test.sh <Dockerfile> <claude|none|opencode>
set -euo pipefail

dockerfile="${1:?usage: smoke-test.sh <Dockerfile> <claude|none|opencode>}"
agent="${2:?usage: smoke-test.sh <Dockerfile> <claude|none|opencode>}"

fail() {
  echo "❌ $1" >&2
  exit 1
}

# Prints an ARG's default from the Dockerfile, failing if it has none. Assign
# its output to a variable before use: set -e ignores a failed substitution
# inside another command's arguments.
arg_default() {
  local value
  value=$(sed -n "s/^ARG $1=//p" "${dockerfile}")
  [[ -n "${value}" ]] || fail "no default for ARG $1 in ${dockerfile}"
  echo "${value}"
}

check_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 not found on PATH"
  echo "✅ $1 present"
}

# Fails unless the output of a command contains the expected text
check_output() {
  local expected="$1" output
  shift
  output=$("$@" 2>&1) || fail "$* exited non-zero: ${output}"
  [[ "${output}" == *"${expected}"* ]] || fail "$* printed '${output}', expected '${expected}'"
  echo "✅ $* → ${output}"
}

echo "▶️ Checking the base image"
# shellcheck source=/dev/null
. /etc/os-release
ubuntu_version=$(arg_default UBUNTU_VERSION)
[[ "${VERSION_ID}" == "${ubuntu_version}" ]] || fail "Ubuntu ${VERSION_ID}, expected ${ubuntu_version}"
echo "✅ Ubuntu ${VERSION_ID}"

echo "▶️ Checking apt-installed tooling"
for cmd in curl git; do
  check_cmd "${cmd}"
done

echo "▶️ Checking Python"
python_version=$(arg_default PYTHON_VERSION)
check_output "Python ${python_version}." "python${python_version}" --version
venv_dir=$(mktemp -d)
"python${python_version}" -m venv "${venv_dir}" || fail "python${python_version} -m venv failed"
rm -rf "${venv_dir}"
echo "✅ python${python_version} -m venv works"

echo "▶️ Checking Node.js"
node_version=$(arg_default NODE_VERSION)
check_output "v${node_version}." node --version
check_cmd npm

echo "▶️ Checking the ${agent} agent"
case "${agent}" in
  claude)
    claude_code_version=$(arg_default CLAUDE_CODE_VERSION)
    check_output "${claude_code_version}" timeout 60 claude --version
    ;;
  none)
    for cmd in claude opencode; do
      ! command -v "${cmd}" >/dev/null 2>&1 || fail "${cmd} installed with AGENT=none"
    done
    echo "✅ no agent installed"
    ;;
  opencode)
    opencode_version=$(arg_default OPENCODE_VERSION)
    check_output "${opencode_version}" timeout 60 opencode --version
    ;;
  *)
    fail "unknown agent: ${agent}"
    ;;
esac

echo "✅ all smoke tests passed"
