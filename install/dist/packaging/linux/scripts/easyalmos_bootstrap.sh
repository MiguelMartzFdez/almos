#!/usr/bin/env bash
set -euo pipefail

export EASYALMOS_SCRIPT_ROOT="${EASYALMOS_SCRIPT_ROOT:-/usr/lib/easyalmos}"
export EASYALMOS_INSTALL_ROOT="${EASYALMOS_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/easyalmos}"
export EASYALMOS_ENV_FILE="${EASYALMOS_ENV_FILE:-$EASYALMOS_SCRIPT_ROOT/shared/almos.yaml}"
export EASYALMOS_VERSION_FILE="${EASYALMOS_VERSION_FILE:-$EASYALMOS_SCRIPT_ROOT/shared/version.txt}"
export EASYALMOS_ICON_SOURCE="${EASYALMOS_ICON_SOURCE:-/usr/share/pixmaps/almos_icon.png}"
export EASYALMOS_BUNDLED_MICROMAMBA="${EASYALMOS_BUNDLED_MICROMAMBA:-$EASYALMOS_SCRIPT_ROOT/bootstrap/micromamba}"
export EASYALMOS_SKIP_APPLICATION_DESKTOP="${EASYALMOS_SKIP_APPLICATION_DESKTOP:-1}"
export EASYALMOS_SKIP_DESKTOP_SHORTCUT="${EASYALMOS_SKIP_DESKTOP_SHORTCUT:-1}"
NOTICE_PID=""
CURRENT_VERSION_FILE="$EASYALMOS_VERSION_FILE"
INSTALLED_VERSION_FILE="$EASYALMOS_INSTALL_ROOT/cache/installed-version.txt"
MICROMAMBA_BIN="$EASYALMOS_INSTALL_ROOT/bin/micromamba"
ENV_PREFIX="$EASYALMOS_INSTALL_ROOT/envs/almos"
ENV_PYTHON="$ENV_PREFIX/bin/python"

start_notice() {
  local text="$1"

  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    return
  fi

  if command -v zenity >/dev/null 2>&1; then
    (
      zenity --info \
        --title="EasyALMOS" \
        --text="$text" \
        --width=420
    ) >/dev/null 2>&1 &
    NOTICE_PID="$!"
    return
  fi

  if command -v xmessage >/dev/null 2>&1; then
    (
      xmessage -center "$text"
    ) >/dev/null 2>&1 &
    NOTICE_PID="$!"
  fi
}

stop_installing_notice() {
  if [[ -n "$NOTICE_PID" ]] && kill -0 "$NOTICE_PID" >/dev/null 2>&1; then
    kill "$NOTICE_PID" >/dev/null 2>&1 || true
    wait "$NOTICE_PID" 2>/dev/null || true
  fi
}

if [[ "${1:-}" == "--uninstall-user-data" ]]; then
  exec "$EASYALMOS_SCRIPT_ROOT/scripts/uninstall_easyalmos.sh"
fi

if [[ "${1:-}" == "--uninstall" ]]; then
  exec "$EASYALMOS_SCRIPT_ROOT/scripts/uninstall_easyalmos_full.sh"
fi

LAUNCH_LOCK_SCRIPT="$EASYALMOS_SCRIPT_ROOT/shared/launch_lock.sh"
if [[ ! -r "$LAUNCH_LOCK_SCRIPT" ]]; then
  echo "EasyALMOS launch lock helper is missing: $LAUNCH_LOCK_SCRIPT" >&2
  exit 1
fi
source "$LAUNCH_LOCK_SCRIPT"
mkdir -p "$EASYALMOS_INSTALL_ROOT/cache"
LAUNCH_LOCK_DIR="$EASYALMOS_INSTALL_ROOT/cache/launch.lock"
if ! acquire_launch_lock "$LAUNCH_LOCK_DIR"; then
  echo "EasyALMOS is already starting." >&2
  exit 0
fi
trap 'release_launch_lock "$LAUNCH_LOCK_DIR"' EXIT

current_version=""
if [[ -f "$CURRENT_VERSION_FILE" ]]; then
  current_version="$(tr -d '\r\n' < "$CURRENT_VERSION_FILE")"
fi

installed_version=""
if [[ -f "$INSTALLED_VERSION_FILE" ]]; then
  installed_version="$(tr -d '\r\n' < "$INSTALLED_VERSION_FILE")"
fi

has_existing_install=0
if [[ -x "$MICROMAMBA_BIN" || -d "$ENV_PREFIX" || -n "$installed_version" ]]; then
  has_existing_install=1
fi

need_install=0
install_reason="first_install"
if [[ ! -x "$MICROMAMBA_BIN" || ! -d "$ENV_PREFIX" || ! -x "$ENV_PYTHON" ]]; then
  need_install=1
  if [[ "$has_existing_install" == "1" ]]; then
    install_reason="repair"
  fi
fi
if [[ "$has_existing_install" == "1" && -n "$current_version" && "$current_version" != "$installed_version" ]]; then
  need_install=1
  install_reason="update"
fi

if [[ "$need_install" == "1" ]]; then
  install_notice="EasyALMOS is being set up for the first time. This may take a few minutes. Please keep this window open."
  install_success_message=""

  if [[ "$install_reason" == "update" ]]; then
    install_notice="EasyALMOS found an existing installation and needs to update its private runtime. Installed version: ${installed_version:-unknown}. New version: ${current_version:-unknown}. This may take a few minutes. Please keep this window open."
    install_success_message="EasyALMOS finished updating its private runtime successfully. Please open EasyALMOS again to start the application."
  elif [[ "$install_reason" == "repair" ]]; then
    install_notice="EasyALMOS found an existing installation, but its private runtime is incomplete or damaged. EasyALMOS will repair the private runtime now. This may take a few minutes. Please keep this window open."
    install_success_message="EasyALMOS finished repairing its private runtime successfully. Please open EasyALMOS again to start the application."
  else
    install_success_message="EasyALMOS finished installing successfully. Please open EasyALMOS again to start the application."
  fi

  start_notice "$install_notice"
  trap stop_installing_notice EXIT
  "$EASYALMOS_SCRIPT_ROOT/scripts/install_easyalmos.sh"
  stop_installing_notice
  trap - EXIT
  if [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    if command -v zenity >/dev/null 2>&1; then
      zenity --info --title="EasyALMOS" --text="$install_success_message" --width=420 >/dev/null 2>&1 || true
    elif command -v xmessage >/dev/null 2>&1; then
      xmessage -center "$install_success_message" >/dev/null 2>&1 || true
    fi
  fi
  exit 0
fi

release_launch_lock "$LAUNCH_LOCK_DIR"
trap - EXIT
exec "$EASYALMOS_SCRIPT_ROOT/scripts/launch_easyalmos.sh"
