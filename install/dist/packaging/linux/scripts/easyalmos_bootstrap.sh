#!/usr/bin/env bash
set -euo pipefail

export EASYALMOS_SYSTEM_ROOT="${EASYALMOS_SYSTEM_ROOT:-/opt/easyalmos}"
export EASYALMOS_INSTALL_ROOT="$EASYALMOS_SYSTEM_ROOT"
export EASYALMOS_SCRIPT_ROOT="${EASYALMOS_SCRIPT_ROOT:-/usr/lib/easyalmos}"
export EASYALMOS_ENV_FILE="${EASYALMOS_ENV_FILE:-$EASYALMOS_SCRIPT_ROOT/shared/almos.yaml}"
export EASYALMOS_ICON_SOURCE="${EASYALMOS_ICON_SOURCE:-/usr/share/pixmaps/easyalmos.png}"
export EASYALMOS_BUNDLED_MICROMAMBA="${EASYALMOS_BUNDLED_MICROMAMBA:-$EASYALMOS_SCRIPT_ROOT/bootstrap/micromamba}"

retry_runtime_setup() {
  local installer="$EASYALMOS_SCRIPT_ROOT/scripts/install_easyalmos_system.sh"

  if [[ ! -x "$installer" ]]; then
    return 1
  fi

  if command -v pkexec >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    pkexec env \
      EASYALMOS_SYSTEM_ROOT="$EASYALMOS_SYSTEM_ROOT" \
      EASYALMOS_INSTALL_ROOT="$EASYALMOS_INSTALL_ROOT" \
      EASYALMOS_SCRIPT_ROOT="$EASYALMOS_SCRIPT_ROOT" \
      EASYALMOS_ENV_FILE="$EASYALMOS_ENV_FILE" \
      EASYALMOS_ICON_SOURCE="$EASYALMOS_ICON_SOURCE" \
      EASYALMOS_BUNDLED_MICROMAMBA="$EASYALMOS_BUNDLED_MICROMAMBA" \
      "$installer"
    return $?
  fi

  if command -v sudo >/dev/null 2>&1; then
    sudo env \
      EASYALMOS_SYSTEM_ROOT="$EASYALMOS_SYSTEM_ROOT" \
      EASYALMOS_INSTALL_ROOT="$EASYALMOS_INSTALL_ROOT" \
      EASYALMOS_SCRIPT_ROOT="$EASYALMOS_SCRIPT_ROOT" \
      EASYALMOS_ENV_FILE="$EASYALMOS_ENV_FILE" \
      EASYALMOS_ICON_SOURCE="$EASYALMOS_ICON_SOURCE" \
      EASYALMOS_BUNDLED_MICROMAMBA="$EASYALMOS_BUNDLED_MICROMAMBA" \
      "$installer"
    return $?
  fi

  return 1
}

if [[ ! -d "$EASYALMOS_SYSTEM_ROOT/envs/almos" ]]; then
  echo "EasyALMOS runtime is not installed at $EASYALMOS_SYSTEM_ROOT; trying to set it up now." >&2
  retry_runtime_setup || {
    echo "EasyALMOS runtime setup failed. Check $EASYALMOS_SYSTEM_ROOT/logs/install-error.log." >&2
    exit 1
  }
fi

exec "$EASYALMOS_SCRIPT_ROOT/scripts/launch_easyalmos.sh"
