#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../launch_lock.sh"

TEST_DIR="$(mktemp -d -p "$PWD")"
case "$TEST_DIR" in
  "$PWD"/*) ;;
  *) echo "Unexpected test directory: $TEST_DIR" >&2; exit 1 ;;
esac
trap 'rm -rf "$TEST_DIR"' EXIT
LOCK_DIR="$TEST_DIR/launch.lock"

acquire_launch_lock "$LOCK_DIR"
if acquire_launch_lock "$LOCK_DIR"; then
  echo "An active launch lock was acquired twice." >&2
  exit 1
fi
release_launch_lock "$LOCK_DIR"

mkdir "$LOCK_DIR"
printf '%s\n' 99999999 >"$LOCK_DIR/pid"
acquire_launch_lock "$LOCK_DIR"
release_launch_lock "$LOCK_DIR"

mkdir "$LOCK_DIR"
acquire_launch_lock "$LOCK_DIR"
release_launch_lock "$LOCK_DIR"

echo "Launch lock tests passed."
