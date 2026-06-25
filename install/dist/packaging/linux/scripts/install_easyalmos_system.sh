#!/usr/bin/env bash
set -euo pipefail

SYSTEM_ROOT="${EASYALMOS_SYSTEM_ROOT:-/opt/easyalmos}"
BIN_DIR="$SYSTEM_ROOT/bin"
ENV_PREFIX="$SYSTEM_ROOT/envs/almos"
LOG_DIR="$SYSTEM_ROOT/logs"
SHARE_DIR="$SYSTEM_ROOT/share"
ICON_DIR="$SHARE_DIR/icons"
SCRIPT_ROOT="${EASYALMOS_SCRIPT_ROOT:-/usr/lib/easyalmos}"
ENV_FILE="${EASYALMOS_ENV_FILE:-$SCRIPT_ROOT/shared/almos.yaml}"
ICON_SOURCE="${EASYALMOS_ICON_SOURCE:-/usr/share/pixmaps/easyalmos.png}"
ICON_TARGET="$ICON_DIR/easyalmos.png"
BOOTSTRAP_MICROMAMBA="${EASYALMOS_BUNDLED_MICROMAMBA:-$SCRIPT_ROOT/bootstrap/micromamba}"
MICROMAMBA_TARBALL_URL="${MICROMAMBA_TARBALL_URL:-https://micro.mamba.pm/api/micromamba/linux-64/latest}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command tar

DOWNLOAD_TOOL=""
if command -v curl >/dev/null 2>&1; then
  DOWNLOAD_TOOL="curl"
elif command -v wget >/dev/null 2>&1; then
  DOWNLOAD_TOOL="wget"
else
  echo "Either curl or wget is required to install EasyALMOS." >&2
  exit 1
fi

mkdir -p "$BIN_DIR" "$LOG_DIR" "$ICON_DIR"

INSTALL_LOG="$LOG_DIR/install.log"
ERROR_LOG="$LOG_DIR/install-error.log"
: > "$INSTALL_LOG"
: > "$ERROR_LOG"

log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" | tee -a "$INSTALL_LOG"
}

run_and_log() {
  log "Running: $*"
  if ! "$@" 2> >(tee -a "$ERROR_LOG" >&2) | tee -a "$INSTALL_LOG"; then
    log "Command failed: $*"
    exit 1
  fi
}

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

log "Installing EasyALMOS system runtime into $SYSTEM_ROOT"
log "Logs: $INSTALL_LOG"
if [[ -x "$BOOTSTRAP_MICROMAMBA" ]]; then
  log "Using bundled Micromamba bootstrap from $BOOTSTRAP_MICROMAMBA"
  install -m 0755 "$BOOTSTRAP_MICROMAMBA" "$BIN_DIR/micromamba"
else
  log "Downloading Micromamba bootstrap..."

  MICROMAMBA_ARCHIVE="$TMP_DIR/micromamba.tar.bz2"
  if [[ "$DOWNLOAD_TOOL" == "curl" ]]; then
    run_and_log curl -L "$MICROMAMBA_TARBALL_URL" -o "$MICROMAMBA_ARCHIVE"
  else
    run_and_log wget -O "$MICROMAMBA_ARCHIVE" "$MICROMAMBA_TARBALL_URL"
  fi

  run_and_log tar -xjf "$MICROMAMBA_ARCHIVE" -C "$TMP_DIR"

  if [[ ! -f "$TMP_DIR/bin/micromamba" ]]; then
    echo "Micromamba archive did not contain bin/micromamba" >&2
    exit 1
  fi

  install -m 0755 "$TMP_DIR/bin/micromamba" "$BIN_DIR/micromamba"
fi

log "Creating ALMOS environment..."
run_and_log "$BIN_DIR/micromamba" create -y -p "$ENV_PREFIX" -f "$ENV_FILE"

if [[ -f "$ICON_SOURCE" ]]; then
  log "Installing icon copy into system runtime..."
  install -m 0644 "$ICON_SOURCE" "$ICON_TARGET"
fi

log "EasyALMOS system runtime installation completed."
log "Runtime root: $SYSTEM_ROOT"
log "Error log: $ERROR_LOG"
