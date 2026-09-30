#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_SCRIPT="$SCRIPT_DIR/../scripts/easyalmos_bootstrap.sh"
TEST_DIR="$(mktemp -d -p "$PWD")"
case "$TEST_DIR" in
  "$PWD"/*) ;;
  *) echo "Unexpected test directory: $TEST_DIR" >&2; exit 1 ;;
esac
trap 'rm -rf "$TEST_DIR"' EXIT

mkdir -p "$TEST_DIR/scripts" "$TEST_DIR/shared" \
  "$TEST_DIR/runtime/bin" "$TEST_DIR/runtime/envs/almos/bin"
cp "$SCRIPT_DIR/../../shared/launch_lock.sh" "$TEST_DIR/shared/launch_lock.sh"
printf '%s\n' 'test-version' >"$TEST_DIR/shared/version.txt"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TEST_DIR/runtime/bin/micromamba"
printf '#!/usr/bin/env bash\nexit 0\n' >"$TEST_DIR/runtime/envs/almos/bin/python"
chmod +x "$TEST_DIR/runtime/bin/micromamba" "$TEST_DIR/runtime/envs/almos/bin/python"

cat >"$TEST_DIR/scripts/install_easyalmos.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' install >>"$EASYALMOS_TEST_EVENTS"
sleep "${EASYALMOS_TEST_INSTALL_DELAY:-0}"
mkdir -p "$(dirname "$EASYALMOS_INSTALLED_VERSION_FILE")"
cp "$EASYALMOS_VERSION_FILE" "$EASYALMOS_INSTALLED_VERSION_FILE"
EOF
cat >"$TEST_DIR/scripts/launch_easyalmos.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' launch >>"$EASYALMOS_TEST_EVENTS"
EOF
chmod +x "$TEST_DIR/scripts/"*.sh

export EASYALMOS_SCRIPT_ROOT="$TEST_DIR"
export EASYALMOS_INSTALL_ROOT="$TEST_DIR/runtime"
export EASYALMOS_ENV_FILE="$TEST_DIR/shared/almos.yaml"
export EASYALMOS_VERSION_FILE="$TEST_DIR/shared/version.txt"
export EASYALMOS_INSTALLED_VERSION_FILE="$TEST_DIR/runtime/cache/installed-version.txt"
export EASYALMOS_TEST_EVENTS="$TEST_DIR/events"

bash "$BOOTSTRAP_SCRIPT"
if [[ "$(cat "$EASYALMOS_TEST_EVENTS")" != "install" ]]; then
  echo "A runtime without a version marker was launched instead of installed." >&2
  exit 1
fi

bash "$BOOTSTRAP_SCRIPT"
if [[ "$(cat "$EASYALMOS_TEST_EVENTS")" != $'install\nlaunch' ]]; then
  echo "An up-to-date runtime was not launched." >&2
  exit 1
fi

: >"$EASYALMOS_TEST_EVENTS"
rm "$EASYALMOS_INSTALLED_VERSION_FILE"
export EASYALMOS_TEST_INSTALL_DELAY=2
bash "$BOOTSTRAP_SCRIPT" &
first_bootstrap_pid=$!
while [[ ! -f "$TEST_DIR/runtime/cache/launch.lock/pid" ]]; do
  sleep 0.1
done
bash "$BOOTSTRAP_SCRIPT"
wait "$first_bootstrap_pid"
if [[ "$(cat "$EASYALMOS_TEST_EVENTS")" != "install" ]]; then
  echo "Concurrent launches ran more than one installation." >&2
  exit 1
fi

echo "Linux bootstrap version tests passed."
