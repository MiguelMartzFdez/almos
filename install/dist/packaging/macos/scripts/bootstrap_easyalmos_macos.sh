#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOURCES_DIR="$APP_ROOT/Resources"
SHARED_DIR="$RESOURCES_DIR/shared"
BOOTSTRAP_DIR="$RESOURCES_DIR/bootstrap"

APP_SUPPORT_DIR="${HOME}/Library/ApplicationSupport/EasyALMOS"
WORK_DIR="${APP_SUPPORT_DIR}/workspace"
BIN_DIR="$APP_SUPPORT_DIR/bin"
ENV_PREFIX="$APP_SUPPORT_DIR/envs/almos"
MAMBA_ROOT_PREFIX="$APP_SUPPORT_DIR/micromamba-root"
LOG_DIR="$APP_SUPPORT_DIR/logs"
STATE_DIR="$APP_SUPPORT_DIR/state"
LOCK_DIR="$STATE_DIR/launch.lock"
VERSION_FILE="$SHARED_DIR/version.txt"
INSTALLED_VERSION_FILE="$STATE_DIR/installed-version.txt"
ENV_FILE="$SHARED_DIR/almos.yaml"
INSTALL_LOG="$LOG_DIR/install.log"
INSTALL_ERR_LOG="$LOG_DIR/install-error.log"
RUNTIME_LOG="$LOG_DIR/runtime.log"
RUNTIME_ERR_LOG="$LOG_DIR/runtime-error.log"
MICROMAMBA_BIN="$BIN_DIR/micromamba"
ENV_PYTHON="$ENV_PREFIX/bin/python"
ENV_PYTHONW="$ENV_PREFIX/bin/pythonw"
NOTICE_PID=""

mkdir -p "$BIN_DIR" "$LOG_DIR" "$STATE_DIR"
mkdir -p "$WORK_DIR"

log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" >>"$INSTALL_LOG"
}

runtime_log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" >>"$RUNTIME_LOG"
}

clear_quarantine_attribute() {
  local target="$1"
  if command -v xattr >/dev/null 2>&1; then
    xattr -dr com.apple.quarantine "$target" >/dev/null 2>&1 || true
  fi
}

configure_private_environment() {
  local existing_path
  existing_path="${PATH:-}"
  export PATH="$ENV_PREFIX/bin${existing_path:+:$existing_path}"
  export DYLD_LIBRARY_PATH="$ENV_PREFIX/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
  export XDG_DATA_DIRS="$ENV_PREFIX/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
  export GI_TYPELIB_PATH="$ENV_PREFIX/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
  export CONDA_PREFIX="$ENV_PREFIX"
  export CONDA_DEFAULT_ENV="almos"
  export CONDA_SHLVL="1"
  export QT_OPENGL="software"
  export QTWEBENGINE_DISABLE_SANDBOX="1"
  export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-gpu-compositing"
}

show_error_dialog() {
  local message="$1"
  osascript -e "display dialog \"$message\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
}

macos_major_version() {
  sw_vers -productVersion 2>/dev/null | awk -F. '{ print $1 }'
}

validate_macos_version() {
  local major_version
  major_version="$(macos_major_version)"
  if [[ -z "$major_version" ]]; then
    echo "Could not determine macOS version." >>"$INSTALL_ERR_LOG"
    return 1
  fi
  if [[ "$major_version" -lt 11 ]]; then
    echo "Unsupported macOS version: $(sw_vers -productVersion 2>/dev/null || true). EasyALMOS requires macOS 11 or newer." >>"$INSTALL_ERR_LOG"
    return 1
  fi
}

start_notice() {
  local text="$1"
  stop_notice
  (
    osascript -e "display dialog \"$text\" buttons {\"OK\"} default button \"OK\" giving up after 86400 with icon note"
  ) >/dev/null 2>&1 &
  NOTICE_PID="$!"
}

stop_notice() {
  if [[ -n "$NOTICE_PID" ]] && kill -0 "$NOTICE_PID" >/dev/null 2>&1; then
    kill "$NOTICE_PID" >/dev/null 2>&1 || true
    wait "$NOTICE_PID" 2>/dev/null || true
  fi
  NOTICE_PID=""
}

cleanup() {
  stop_notice
  rm -rf "$LOCK_DIR"
}

if ! mkdir "$LOCK_DIR" >/dev/null 2>&1; then
  osascript -e 'display notification "EasyALMOS is already starting..." with title "EasyALMOS"' >/dev/null 2>&1 || true
  exit 0
fi
trap cleanup EXIT

: >"$INSTALL_LOG"
: >"$INSTALL_ERR_LOG"
: >"$RUNTIME_LOG"
: >"$RUNTIME_ERR_LOG"

run_install_command() {
  log "Running: $*"
  if ! "$@" >>"$INSTALL_LOG" 2>>"$INSTALL_ERR_LOG"; then
    log "Command failed: $*"
    return 1
  fi
}

current_version=""
if [[ -f "$VERSION_FILE" ]]; then
  current_version="$(tr -d '\r\n' < "$VERSION_FILE")"
fi

installed_version=""
if [[ -f "$INSTALLED_VERSION_FILE" ]]; then
  installed_version="$(tr -d '\r\n' < "$INSTALLED_VERSION_FILE")"
fi

need_install=0
if [[ ! -x "$MICROMAMBA_BIN" || ! -d "$ENV_PREFIX" ]]; then
  need_install=1
fi
if [[ -n "$current_version" && "$current_version" != "$installed_version" ]]; then
  need_install=1
fi

require_download_tool() {
  if command -v curl >/dev/null 2>&1; then
    printf '%s\n' "curl"
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    printf '%s\n' "wget"
    return
  fi
  return 1
}

detect_micromamba_platform() {
  case "$(uname -m)" in
    arm64|aarch64)
      printf '%s\n' "osx-arm64"
      ;;
    x86_64)
      printf '%s\n' "osx-64"
      ;;
    *)
      return 1
      ;;
  esac
}

detect_machine_arch() {
  uname -m
}

install_micromamba() {
  local platform asset_name bundled_asset downloader tmp_dir archive_path

  platform="$(detect_micromamba_platform)"
  asset_name="micromamba-$platform"
  bundled_asset="$BOOTSTRAP_DIR/$asset_name"

  if [[ -x "$bundled_asset" ]]; then
    log "Using bundled Micromamba asset: $bundled_asset"
    install -m 0755 "$bundled_asset" "$MICROMAMBA_BIN"
    clear_quarantine_attribute "$MICROMAMBA_BIN"
    return 0
  fi

  downloader="$(require_download_tool)" || {
    echo "No download tool available for Micromamba bootstrap." >>"$INSTALL_ERR_LOG"
    return 1
  }

  tmp_dir="$(mktemp -d)"
  archive_path="$tmp_dir/micromamba.tar.bz2"
  log "Downloading Micromamba for $platform"

  if [[ "$downloader" == "curl" ]]; then
    run_install_command curl -L "https://micro.mamba.pm/api/micromamba/$platform/latest" -o "$archive_path" || {
      rm -rf "$tmp_dir"
      return 1
    }
  else
    run_install_command wget -O "$archive_path" "https://micro.mamba.pm/api/micromamba/$platform/latest" || {
      rm -rf "$tmp_dir"
      return 1
    }
  fi

  run_install_command tar -xjf "$archive_path" -C "$tmp_dir" || {
    rm -rf "$tmp_dir"
    return 1
  }

  if [[ ! -f "$tmp_dir/bin/micromamba" ]]; then
    echo "Micromamba archive did not contain bin/micromamba" >>"$INSTALL_ERR_LOG"
    rm -rf "$tmp_dir"
    return 1
  fi

  install -m 0755 "$tmp_dir/bin/micromamba" "$MICROMAMBA_BIN"
  clear_quarantine_attribute "$MICROMAMBA_BIN"
  rm -rf "$tmp_dir"
}

install_runtime() {
  local platform machine_arch macos_version

  validate_macos_version || return 1
  platform="$(detect_micromamba_platform)" || return 1
  machine_arch="$(detect_machine_arch)"
  macos_version="$(sw_vers -productVersion 2>/dev/null || true)"

  log "Preparing EasyALMOS runtime at $APP_SUPPORT_DIR"
  log "macOS version: $macos_version"
  log "Machine architecture: $machine_arch"
  log "Micromamba platform: $platform"

  if [[ -d "$ENV_PREFIX" ]]; then
    log "Removing previous ALMOS environment"
    rm -rf "$ENV_PREFIX"
  fi

  install_micromamba || return 1
  chmod 0755 "$MICROMAMBA_BIN" >/dev/null 2>&1 || true
  clear_quarantine_attribute "$MICROMAMBA_BIN"

  log "Creating ALMOS environment from $ENV_FILE"
  export MAMBA_ROOT_PREFIX
  export CONDA_SUBDIR="$platform"
  run_install_command "$MICROMAMBA_BIN" create -y -p "$ENV_PREFIX" -f "$ENV_FILE" || return 1
  run_install_command "$MICROMAMBA_BIN" install -y -p "$ENV_PREFIX" python.app || return 1

  if [[ -n "$current_version" ]]; then
    printf '%s\n' "$current_version" > "$INSTALLED_VERSION_FILE"
  fi
}

launch_easyalmos() {
  local launcher_python
  runtime_log "Launching EasyALMOS from $ENV_PREFIX"
  runtime_log "Using working directory at $WORK_DIR"
  launcher_python="$ENV_PYTHON"
  if [[ -x "$ENV_PYTHONW" ]]; then
    launcher_python="$ENV_PYTHONW"
  fi
  runtime_log "Using Python interpreter at $launcher_python"
  if [[ ! -x "$launcher_python" ]]; then
    echo "EasyALMOS Python launcher not found at $launcher_python" >>"$RUNTIME_ERR_LOG"
    return 1
  fi
  configure_private_environment
  cd "$WORK_DIR"
  "$launcher_python" -c "from almos.easyalmos import main; raise SystemExit(main() or 0)" \
    >>"$RUNTIME_LOG" 2>>"$RUNTIME_ERR_LOG"
}

if [[ "$need_install" == "1" ]]; then
  start_notice "EasyALMOS is being set up for the first time.\n\nThis may take a few minutes while the private runtime is installed.\n\nPlease keep this window open."
  if ! install_runtime; then
    show_error_dialog "EasyALMOS installation failed. Check the logs in ~/Library/ApplicationSupport/EasyALMOS/logs."
    exit 1
  fi
fi

start_notice "EasyALMOS is opening...\n\nPlease wait.\n\nThe first launch may take a little longer.\n\nIMPORTANT: on macOS, you should work inside the EasyALMOS workspace:\n$WORK_DIR\n\nMove your CSV files and project folders there before running workflows. Do not work directly from Downloads, Desktop, or external folders."
if ! launch_easyalmos; then
  show_error_dialog "EasyALMOS could not start. Check the logs in ~/Library/ApplicationSupport/EasyALMOS/logs."
  exit 1
fi
