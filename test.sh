#!/usr/bin/env bash
#
# test.sh — run claudevm's test suite. This is the only supported way to
# run tests in this repo; never invoke pytest directly (see CLAUDE.md).
#
# Usage:
#   ./test.sh                     # everything: unit + integration
#   ./test.sh unit                # fast tests only, no real VMs -- safe for CI
#   ./test.sh integration         # slow tests only, boots real VMs, local-only
#   ./test.sh unit -- -k test_foo # forward extra args straight to pytest
#
# The integration tier boots real Lima VMs and can take several minutes.
# There is no way to opt out of it by default -- `./test.sh unit` is how
# you limit a run to the fast tier.
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$("$REPO_DIR/tools/venv")"

mode="all"
if [ $# -gt 0 ] && [ "$1" != "--" ]; then
  mode="$1"
  shift
fi
if [ "${1:-}" = "--" ]; then
  shift
fi

case "$mode" in
  all) marker_args=() ;;
  unit) marker_args=(-m "not integration") ;;
  integration) marker_args=(-m "integration") ;;
  *)
    echo "Usage: $0 [all|integration|unit] [-- pytest-args...]" >&2
    exit 1
    ;;
esac

cd "$REPO_DIR"
# `${marker_args[@]}` alone segfaults "unbound variable" under `set -u` on
# bash 3.2 (macOS's default /bin/bash) when the array is empty (the `all`
# case) -- this expansion is the standard 3.2-safe workaround.
exec "$VENV_DIR/bin/pytest" ${marker_args[@]+"${marker_args[@]}"} "$@"
