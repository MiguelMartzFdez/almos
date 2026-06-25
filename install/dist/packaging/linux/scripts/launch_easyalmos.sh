#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${EASYALMOS_INSTALL_ROOT:-${EASYALMOS_SYSTEM_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/easyalmos}}"
MICROMAMBA_BIN="$INSTALL_ROOT/bin/micromamba"
ENV_PREFIX="$INSTALL_ROOT/envs/almos"
ENV_PYTHON="$ENV_PREFIX/bin/python"
USER_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/easyalmos"
LOG_DIR="$USER_STATE_DIR/logs"
RUNTIME_LOG="$LOG_DIR/runtime.log"
NOTICE_PID=""

mkdir -p "$LOG_DIR"

log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" >> "$RUNTIME_LOG"
}

configure_private_environment() {
  local existing_path
  existing_path="${PATH:-}"
  export PATH="$ENV_PREFIX/bin${existing_path:+:$existing_path}"
  export LD_LIBRARY_PATH="$ENV_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
  export XDG_DATA_DIRS="$ENV_PREFIX/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
  export GI_TYPELIB_PATH="$ENV_PREFIX/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
  export CONDA_PREFIX="$ENV_PREFIX"
  export CONDA_DEFAULT_ENV="almos"
  export CONDA_SHLVL="1"
}

start_opening_notice() {
  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    return
  fi

  if command -v zenity >/dev/null 2>&1; then
    (
      zenity --info \
        --title="EasyALMOS" \
        --text="EasyALMOS is opening..." \
        --width=320 \
        --no-wrap
    ) >/dev/null 2>&1 &
    NOTICE_PID="$!"
    return
  fi

  if command -v xmessage >/dev/null 2>&1; then
    (
      xmessage -center "EasyALMOS is opening..."
    ) >/dev/null 2>&1 &
    NOTICE_PID="$!"
  fi
}

stop_opening_notice() {
  if [[ -n "$NOTICE_PID" ]] && kill -0 "$NOTICE_PID" >/dev/null 2>&1; then
    kill "$NOTICE_PID" >/dev/null 2>&1 || true
    wait "$NOTICE_PID" 2>/dev/null || true
  fi
}

if [[ ! -d "$ENV_PREFIX" ]]; then
  echo "ALMOS environment not found at $ENV_PREFIX" >&2
  exit 1
fi

if [[ ! -x "$ENV_PYTHON" ]]; then
  echo "EasyALMOS Python interpreter not found at $ENV_PYTHON" >&2
  exit 1
fi

log "Launching EasyALMOS from $ENV_PREFIX"
log "Using Python interpreter at $ENV_PYTHON"

configure_private_environment
start_opening_notice
trap stop_opening_notice EXIT

LAUNCH_COMMAND=(
  "$ENV_PYTHON"
  -c
  "from almos.easyalmos import main; raise SystemExit(main() or 0)"
)

"${LAUNCH_COMMAND[@]}"
