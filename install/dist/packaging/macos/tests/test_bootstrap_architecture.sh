#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARCHITECTURE_UTILS="$SCRIPT_DIR/../scripts/architecture_utils.sh"

source "$ARCHITECTURE_UTILS"

assert_equals() {
  local expected="$1"
  local actual="$2"
  local message="$3"

  if [[ "$actual" != "$expected" ]]; then
    echo "FAIL: $message" >&2
    echo "  expected: $expected" >&2
    echo "  actual:   $actual" >&2
    exit 1
  fi
}

assert_success() {
  local message="$1"
  shift

  if ! "$@"; then
    echo "FAIL: $message" >&2
    exit 1
  fi
}

assert_failure() {
  local message="$1"
  shift

  if "$@"; then
    echo "FAIL: $message" >&2
    exit 1
  fi
}

assert_equals "osx-arm64" "$(resolve_micromamba_platform arm64 0)" \
  "native Apple Silicon must use the arm64 package channel"
assert_equals "osx-arm64" "$(resolve_micromamba_platform x86_64 1)" \
  "Apple Silicon translated by Rosetta must use the arm64 package channel"
assert_equals "osx-64" "$(resolve_micromamba_platform x86_64 0)" \
  "native Intel must use the Intel package channel"

assert_success \
  "an arm64 environment must match the osx-arm64 channel" \
  environment_architecture_matches_platform arm64 osx-arm64
assert_success \
  "an x86_64 environment must match the osx-64 channel" \
  environment_architecture_matches_platform x86_64 osx-64
assert_failure \
  "an Intel environment must not match the Apple Silicon channel" \
  environment_architecture_matches_platform x86_64 osx-arm64
assert_failure \
  "an unknown machine architecture must be rejected" \
  resolve_micromamba_platform riscv64 0

uname() {
  printf '%s\n' "x86_64"
}

sysctl() {
  if [[ "$*" != "-in sysctl.proc_translated" ]]; then
    return 1
  fi
  printf '%s\n' "1"
}

assert_equals "osx-arm64" "$(detect_micromamba_platform)" \
  "the runtime detector must select arm64 when macOS reports Rosetta translation"

echo "All macOS architecture tests passed."
