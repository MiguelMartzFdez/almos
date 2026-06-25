#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LINUX_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SHARED_ROOT="${EASYALMOS_SHARED_ROOT:-$(cd "$LINUX_ROOT/../shared" && pwd)}"
ENV_FILE="${EASYALMOS_ENV_FILE:-$SHARED_ROOT/almos.yaml}"
WINDOWS_ASSETS_DIR="${EASYALMOS_WINDOWS_ASSETS_DIR:-$(cd "$LINUX_ROOT/../windows/assets" && pwd)}"

INSTALL_ROOT="${EASYALMOS_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/easyalmos}"
BIN_DIR="$INSTALL_ROOT/bin"
ENV_PREFIX="$INSTALL_ROOT/envs/almos"
LOG_DIR="$INSTALL_ROOT/logs"
SHARE_DIR="$INSTALL_ROOT/share"
ICON_DIR="$SHARE_DIR/icons"
ICON_SOURCE="${EASYALMOS_ICON_SOURCE:-$WINDOWS_ASSETS_DIR/almos_icon.png}"
ICON_TARGET="$ICON_DIR/easyalmos.png"
LAUNCHER_TARGET="$BIN_DIR/easyalmos"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_FILE="$APPLICATIONS_DIR/easyalmos.desktop"
MICROMAMBA_TARBALL_URL="${MICROMAMBA_TARBALL_URL:-https://micro.mamba.pm/api/micromamba/linux-64/latest}"
SKIP_APPLICATION_DESKTOP="${EASYALMOS_SKIP_APPLICATION_DESKTOP:-0}"
SKIP_DESKTOP_SHORTCUT="${EASYALMOS_SKIP_DESKTOP_SHORTCUT:-0}"

resolve_desktop_dir() {
  if [[ -n "${XDG_DESKTOP_DIR:-}" ]]; then
    printf '%s\n' "$XDG_DESKTOP_DIR"
    return
  fi

  if command -v xdg-user-dir >/dev/null 2>&1; then
    local detected_dir
    detected_dir="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
    if [[ -n "$detected_dir" ]]; then
      printf '%s\n' "$detected_dir"
      return
    fi
  fi

  printf '%s\n' "$HOME/Desktop"
}

DESKTOP_SHORTCUT_DIR="$(resolve_desktop_dir)"
DESKTOP_SHORTCUT_FILE="$DESKTOP_SHORTCUT_DIR/EasyALMOS.desktop"

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
if [[ "$SKIP_APPLICATION_DESKTOP" != "1" ]]; then
  mkdir -p "$APPLICATIONS_DIR"
fi
if [[ "$SKIP_DESKTOP_SHORTCUT" != "1" && -d "$DESKTOP_SHORTCUT_DIR" ]]; then
  mkdir -p "$DESKTOP_SHORTCUT_DIR"
fi

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

log "Installing EasyALMOS into $INSTALL_ROOT"
log "Logs: $INSTALL_LOG"
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

log "Creating ALMOS environment..."
run_and_log "$BIN_DIR/micromamba" create -y -p "$ENV_PREFIX" -f "$ENV_FILE"

log "Installing launcher..."
install -m 0755 "$SCRIPT_DIR/launch_easyalmos.sh" "$LAUNCHER_TARGET"

if [[ -f "$ICON_SOURCE" ]]; then
  log "Installing icon..."
  install -m 0644 "$ICON_SOURCE" "$ICON_TARGET"
fi

if [[ "$SKIP_APPLICATION_DESKTOP" != "1" ]]; then
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=EasyALMOS
Comment=Launch EasyALMOS with its private environment
Exec=$LAUNCHER_TARGET
TryExec=$LAUNCHER_TARGET
Terminal=false
Path=$INSTALL_ROOT
Icon=$ICON_TARGET
Categories=Science;
EOF

  chmod 0644 "$DESKTOP_FILE"
fi

if [[ "$SKIP_DESKTOP_SHORTCUT" != "1" && -d "$DESKTOP_SHORTCUT_DIR" ]]; then
  log "Creating desktop shortcut..."
  if [[ "$SKIP_APPLICATION_DESKTOP" != "1" ]]; then
    install -m 0755 "$DESKTOP_FILE" "$DESKTOP_SHORTCUT_FILE"
  else
    cat > "$DESKTOP_SHORTCUT_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=EasyALMOS
Comment=Launch EasyALMOS with its private environment
Exec=$LAUNCHER_TARGET
TryExec=$LAUNCHER_TARGET
Terminal=false
Path=$INSTALL_ROOT
Icon=$ICON_TARGET
Categories=Science;
EOF
    chmod 0755 "$DESKTOP_SHORTCUT_FILE"
  fi
fi

if [[ "$SKIP_APPLICATION_DESKTOP" != "1" ]] && command -v update-desktop-database >/dev/null 2>&1; then
  run_and_log update-desktop-database "$(dirname "$DESKTOP_FILE")"
fi

log "EasyALMOS installation completed."
log "Launcher: $LAUNCHER_TARGET"
if [[ "$SKIP_APPLICATION_DESKTOP" != "1" ]]; then
  log "Desktop entry: $DESKTOP_FILE"
fi
if [[ "$SKIP_DESKTOP_SHORTCUT" != "1" && -d "$DESKTOP_SHORTCUT_DIR" ]]; then
  log "Desktop shortcut: $DESKTOP_SHORTCUT_FILE"
fi
log "Error log: $ERROR_LOG"
