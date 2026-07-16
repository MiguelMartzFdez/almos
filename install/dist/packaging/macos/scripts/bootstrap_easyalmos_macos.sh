#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_BUNDLE_PATH="$(cd "$APP_ROOT/.." && pwd)"
RESOURCES_DIR="$APP_ROOT/Resources"
SHARED_DIR="$RESOURCES_DIR/shared"
BOOTSTRAP_DIR="$RESOURCES_DIR/bootstrap"

APP_SUPPORT_DIR="${HOME}/Library/ApplicationSupport/EasyALMOS"
LEGACY_APP_SUPPORT_DIR="${HOME}/Library/Application Support/EasyALMOS"
WORK_DIR="$APP_SUPPORT_DIR/workspace"
MICROMAMBA_DIR="$APP_SUPPORT_DIR/micromamba"
BIN_DIR="$MICROMAMBA_DIR/bin"
MICROMAMBA_BIN="$BIN_DIR/micromamba"
ENV_PREFIX="$APP_SUPPORT_DIR/envs/almos"
CACHE_DIR="$APP_SUPPORT_DIR/cache"
LOG_DIR="$APP_SUPPORT_DIR/logs"
MAMBA_ROOT_PREFIX="$MICROMAMBA_DIR/root"

VERSION_FILE="$SHARED_DIR/version.txt"
INSTALLED_VERSION_FILE="$CACHE_DIR/installed-version.txt"
ENV_FILE="$SHARED_DIR/almos.yaml"
CONDA_ENV_FILE="$CACHE_DIR/env-conda.yaml"
PIP_REQUIREMENTS_FILE="$CACHE_DIR/pip-requirements.txt"
WORKSPACE_README="$WORK_DIR/README.txt"
UNINSTALL_SCRIPT="$APP_SUPPORT_DIR/uninstall_easyalmos.sh"
UNINSTALL_COMMAND="$APP_SUPPORT_DIR/uninstall_easyalmos.command"
INSTALL_LOG="$LOG_DIR/install.log"
INSTALL_ERR_LOG="$LOG_DIR/install-error.log"
RUNTIME_LOG="$LOG_DIR/runtime.log"
RUNTIME_ERR_LOG="$LOG_DIR/runtime-error.log"
LOCK_DIR="$CACHE_DIR/launch.lock"
ENV_PYTHON="$ENV_PREFIX/bin/python"
ENV_PYTHONW="$ENV_PREFIX/bin/pythonw"
ENV_PYTHON_APP="$ENV_PREFIX/python.app/Contents/MacOS/python"
NOTICE_PID=""

ensure_directories() {
  mkdir -p \
    "$APP_SUPPORT_DIR" \
    "$WORK_DIR" \
    "$CACHE_DIR" \
    "$LOG_DIR"
  mkdir -p \
    "$MICROMAMBA_DIR" \
    "$BIN_DIR"
}

write_workspace_readme() {
  cat >"$WORKSPACE_README" <<EOF
EasyALMOS workspace

Place your CSV files and project folders in this workspace before running workflows.

macOS build note:
- EasyALMOS is configured to work inside this private workspace.
- Avoid running workflows directly from Desktop, Downloads, or Documents.
EOF
}

write_uninstallers() {
  cat >"$UNINSTALL_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail

APP_SUPPORT_DIR="$APP_SUPPORT_DIR"
LEGACY_APP_SUPPORT_DIR="\$HOME/Library/Application Support/EasyALMOS"
APP_BUNDLE_PATH="$APP_BUNDLE_PATH"
EXPECTED_APP_SUPPORT_DIR="$HOME/Library/ApplicationSupport/EasyALMOS"
UNINSTALL_LOG="\${TMPDIR:-/tmp}/easyalmos-uninstall.log"

confirm_uninstall() {
  osascript \
    -e 'display dialog "Uninstall EasyALMOS?\n\nThis will remove EasyALMOS.app and ~/Library/Application Support/EasyALMOS." buttons {"Cancel", "Uninstall"} default button "Uninstall" with icon caution' \
    -e 'button returned of result' 2>/dev/null || true
}

show_result() {
  local message="\$1"
  local icon="\$2"
  osascript -e "display dialog \\"\$message\\" buttons {\\"OK\\"} default button \\"OK\\" with icon \$icon" >/dev/null 2>&1 || true
}

abort_if_unexpected_path() {
  local actual_path="\$1"
  local expected_path="\$2"
  local label="\$3"

  if [[ "\$actual_path" != "\$expected_path" ]]; then
    echo "Unexpected \$label path: \$actual_path" >>"\$UNINSTALL_LOG"
    echo "Expected: \$expected_path" >>"\$UNINSTALL_LOG"
    show_result "EasyALMOS uninstall was stopped because the \$label path was unexpected.\n\nCheck this log for details:\n\$UNINSTALL_LOG" stop
    exit 1
  fi
}

if [[ "\$(confirm_uninstall)" != "Uninstall" ]]; then
  exit 0
fi

cd "\$HOME"
: >"\$UNINSTALL_LOG"

echo "Starting EasyALMOS uninstall" >>"\$UNINSTALL_LOG"
echo "App bundle: \$APP_BUNDLE_PATH" >>"\$UNINSTALL_LOG"
echo "Support dir: \$APP_SUPPORT_DIR" >>"\$UNINSTALL_LOG"

abort_if_unexpected_path "\$APP_SUPPORT_DIR" "\$EXPECTED_APP_SUPPORT_DIR" "Application Support"
case "\$APP_BUNDLE_PATH" in
  */EasyALMOS.app) ;;
  *)
    echo "Unexpected app bundle path: \$APP_BUNDLE_PATH" >>"\$UNINSTALL_LOG"
    show_result "EasyALMOS uninstall was stopped because the app bundle path was unexpected.\n\nCheck this log for details:\n\$UNINSTALL_LOG" stop
    exit 1
    ;;
esac

if [[ -d "\$LEGACY_APP_SUPPORT_DIR" && "\$LEGACY_APP_SUPPORT_DIR" != "\$APP_SUPPORT_DIR" ]]; then
  case "\$LEGACY_APP_SUPPORT_DIR" in
    "$HOME/Library/Application Support/EasyALMOS") ;;
    *)
      echo "Unexpected legacy support path: \$LEGACY_APP_SUPPORT_DIR" >>"\$UNINSTALL_LOG"
      show_result "EasyALMOS uninstall was stopped because the legacy support path was unexpected.\n\nCheck this log for details:\n\$UNINSTALL_LOG" stop
      exit 1
      ;;
  esac
fi

osascript -e 'tell application id "com.thealegregroup.easyalmos" to quit' >/dev/null 2>&1 || true
sleep 2

SUPPORT_REMOVED=0
APP_REMOVED=0

if [[ -d "\$APP_SUPPORT_DIR" ]]; then
  rm -rf "\$APP_SUPPORT_DIR" >>"\$UNINSTALL_LOG" 2>&1 || true
fi
if [[ -d "\$LEGACY_APP_SUPPORT_DIR" && "\$LEGACY_APP_SUPPORT_DIR" != "\$APP_SUPPORT_DIR" ]]; then
  rm -rf "\$LEGACY_APP_SUPPORT_DIR" >>"\$UNINSTALL_LOG" 2>&1 || true
fi
if [[ ! -d "\$APP_SUPPORT_DIR" ]]; then
  SUPPORT_REMOVED=1
fi

if [[ -d "\$APP_BUNDLE_PATH" ]]; then
  rm -rf "\$APP_BUNDLE_PATH" >>"\$UNINSTALL_LOG" 2>&1 || true
fi

if [[ ! -d "\$APP_BUNDLE_PATH" ]]; then
  APP_REMOVED=1
fi

if [[ "\$SUPPORT_REMOVED" == "1" && "\$APP_REMOVED" == "1" ]]; then
  show_result "EasyALMOS was uninstalled successfully." note
  exit 0
fi

if [[ "\$SUPPORT_REMOVED" == "1" && "\$APP_REMOVED" != "1" ]]; then
  show_result "EasyALMOS removed its private files, but EasyALMOS.app is still present.\n\nPlease delete /Applications/EasyALMOS.app manually." caution
  exit 1
fi

show_result "EasyALMOS could not be fully uninstalled.\n\nCheck this log for details:\n\$UNINSTALL_LOG" stop
exit 1
EOF

  cat >"$UNINSTALL_COMMAND" <<EOF
#!/usr/bin/env bash
exec "$UNINSTALL_SCRIPT"
EOF

  chmod 0755 "$UNINSTALL_SCRIPT" "$UNINSTALL_COMMAND"
}

log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" >>"$INSTALL_LOG"
}

runtime_log() {
  printf '%s %s\n' "[$(date '+%Y-%m-%d %H:%M:%S')]" "$*" >>"$RUNTIME_LOG"
}

show_error_dialog() {
  local message="$1"
  osascript -e "display dialog \"$message\" buttons {\"OK\"} default button \"OK\" with icon stop" >/dev/null 2>&1 || true
}

show_info_dialog() {
  local message="$1"
  osascript -e "display dialog \"$message\" buttons {\"OK\"} default button \"OK\" with icon note" >/dev/null 2>&1 || true
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

schedule_notice_stop() {
  local pid="$1"
  local delay_seconds="$2"
  if [[ -z "$pid" ]]; then
    return
  fi
  (
    sleep "$delay_seconds"
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
      wait "$pid" 2>/dev/null || true
    fi
  ) >/dev/null 2>&1 &
}

update_notice() {
  local step="$1"
  local message="$2"
  start_notice "EasyALMOS setup in progress.\n\nStep $step of 6:\n$message\n\nPlease keep this window open."
}

cleanup() {
  stop_notice
  rm -rf "$LOCK_DIR"
}

clear_execution_attributes() {
  local target="$1"
  if [[ -e "$target" ]] && command -v xattr >/dev/null 2>&1; then
    xattr -cr "$target" >/dev/null 2>&1 || true
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
  export MAMBA_ROOT_PREFIX
  export EASYALMOS_WORKSPACE_DIR="$WORK_DIR"
  export QT_OPENGL="software"
  export QTWEBENGINE_DISABLE_SANDBOX="1"
  export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-gpu-compositing"
}

configure_build_environment() {
  configure_private_environment
  export PKG_CONFIG_PATH="$ENV_PREFIX/lib/pkgconfig:$ENV_PREFIX/share/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
  export OPENSSL_DIR="$ENV_PREFIX"
  export OPENSSL_INCLUDE_DIR="$ENV_PREFIX/include"
  export OPENSSL_LIB_DIR="$ENV_PREFIX/lib"
}

run_install_command() {
  log "Running: $*"
  if ! "$@" >>"$INSTALL_LOG" 2>>"$INSTALL_ERR_LOG"; then
    log "Command failed: $*"
    return 1
  fi
}

run_environment_create_with_retry() {
  local max_environment_create_attempts=3
  local attempt=1

  while (( attempt <= max_environment_create_attempts )); do
    if run_install_command "$MICROMAMBA_BIN" create -y -p "$ENV_PREFIX" -f "$CONDA_ENV_FILE"; then
      return 0
    fi
    if (( attempt == max_environment_create_attempts )); then
      return 1
    fi
    log "Environment creation attempt $attempt of $max_environment_create_attempts failed; retrying in $((attempt * 5)) seconds."
    sleep "$((attempt * 5))"
    ((attempt++))
  done
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

require_file() {
  local path="$1"
  local description="$2"
  if [[ ! -e "$path" ]]; then
    echo "Missing $description at $path" >>"$INSTALL_ERR_LOG"
    return 1
  fi
}

prepare_split_env_files() {
  rm -f "$CONDA_ENV_FILE" "$PIP_REQUIREMENTS_FILE"
  awk '
    BEGIN { in_pip = 0 }
    /^  - pip:$/ { in_pip = 1; next }
    {
      if (in_pip) {
        if ($0 ~ /^      - /) {
          print substr($0, 9) >> pip_file
          next
        }
        in_pip = 0
      }
      print $0 >> conda_file
    }
  ' conda_file="$CONDA_ENV_FILE" pip_file="$PIP_REQUIREMENTS_FILE" "$ENV_FILE"
}

copy_bundled_micromamba() {
  local platform asset_name bundled_asset

  platform="$(detect_micromamba_platform)" || {
    echo "Unsupported machine architecture: $(uname -m)" >>"$INSTALL_ERR_LOG"
    return 1
  }
  asset_name="micromamba-$platform"
  bundled_asset="$BOOTSTRAP_DIR/$asset_name"

  require_file "$bundled_asset" "bundled Micromamba asset" || return 1
  log "Copying bundled Micromamba from $bundled_asset"
  install -m 0755 "$bundled_asset" "$MICROMAMBA_BIN"
  chmod 0755 "$MICROMAMBA_BIN"
  clear_execution_attributes "$MICROMAMBA_BIN"
  require_file "$MICROMAMBA_BIN" "copied Micromamba binary" || return 1
  run_install_command "$MICROMAMBA_BIN" --version || return 1
}

validate_environment() {
  if [[ ! -x "$ENV_PYTHON" ]]; then
    echo "EasyALMOS Python interpreter was not created at $ENV_PYTHON" >>"$INSTALL_ERR_LOG"
    return 1
  fi
  configure_private_environment
  run_install_command "$ENV_PYTHON" -c "from almos.easyalmos import main" || return 1
}

remove_previous_runtime() {
  log "Removing previous EasyALMOS runtime directories"
  rm -rf "$ENV_PREFIX" "$MAMBA_ROOT_PREFIX"
}

install_runtime() {
  local platform machine_arch macos_version

  ensure_directories
  write_workspace_readme
  write_uninstallers
  validate_macos_version || return 1
  require_file "$ENV_FILE" "shared environment file" || return 1

  platform="$(detect_micromamba_platform)" || return 1
  machine_arch="$(uname -m)"
  macos_version="$(sw_vers -productVersion 2>/dev/null || true)"

  log "Preparing EasyALMOS runtime at $APP_SUPPORT_DIR"
  log "Workspace: $WORK_DIR"
  log "macOS version: $macos_version"
  log "Machine architecture: $machine_arch"
  log "Micromamba platform: $platform"

  update_notice 1 "Creating application folders."
  ensure_directories
  write_workspace_readme
  write_uninstallers

  update_notice 2 "Copying bundled Micromamba."
  copy_bundled_micromamba || return 1

  update_notice 3 "Preparing the private environment definition."
  prepare_split_env_files

  update_notice 4 "Cleaning the previous private runtime."
  remove_previous_runtime
  mkdir -p "$MAMBA_ROOT_PREFIX"

  update_notice 5 "Creating the private EasyALMOS environment."
  export MAMBA_ROOT_PREFIX
  export CONDA_SUBDIR="$platform"
  run_environment_create_with_retry || return 1
  clear_execution_attributes "$ENV_PREFIX"

  update_notice 6 "Installing the macOS Python application launcher."
  run_install_command "$MICROMAMBA_BIN" install -y -p "$ENV_PREFIX" python.app || return 1
  clear_execution_attributes "$ENV_PREFIX"

  if [[ -s "$PIP_REQUIREMENTS_FILE" ]]; then
    update_notice 6 "Installing Python packages."
    configure_build_environment
    run_install_command "$ENV_PYTHON" -m pip install -r "$PIP_REQUIREMENTS_FILE" || return 1
    clear_execution_attributes "$ENV_PREFIX"
  fi

  update_notice 6 "Validating the installed runtime."
  validate_environment || return 1

  if [[ -f "$VERSION_FILE" ]]; then
    tr -d '\r\n' < "$VERSION_FILE" > "$INSTALLED_VERSION_FILE"
  fi
}

launch_easyalmos() {
  local launcher_python

  runtime_log "Launching EasyALMOS from $ENV_PREFIX"
  runtime_log "Using working directory at $WORK_DIR"

  launcher_python="$ENV_PYTHON"
  if [[ -x "$ENV_PYTHONW" ]]; then
    launcher_python="$ENV_PYTHONW"
  elif [[ -x "$ENV_PYTHON_APP" ]]; then
    launcher_python="$ENV_PYTHON_APP"
  fi
  runtime_log "Using Python interpreter at $launcher_python"

  if [[ ! -x "$launcher_python" ]]; then
    echo "EasyALMOS Python launcher not found at $launcher_python" >>"$RUNTIME_ERR_LOG"
    return 1
  fi

  configure_private_environment
  cd "$WORK_DIR"
  rm -rf "$LOCK_DIR"
  trap - EXIT
  exec "$launcher_python" -c "from almos.easyalmos import main; raise SystemExit(main() or 0)" \
    >>"$RUNTIME_LOG" 2>>"$RUNTIME_ERR_LOG"
}

ensure_directories
write_uninstallers

if ! mkdir "$LOCK_DIR" >/dev/null 2>&1; then
  osascript -e 'display notification "EasyALMOS is already starting..." with title "EasyALMOS"' >/dev/null 2>&1 || true
  exit 0
fi
trap cleanup EXIT

current_version=""
if [[ -f "$VERSION_FILE" ]]; then
  current_version="$(tr -d '\r\n' < "$VERSION_FILE")"
fi

installed_version=""
if [[ -f "$INSTALLED_VERSION_FILE" ]]; then
  installed_version="$(tr -d '\r\n' < "$INSTALLED_VERSION_FILE")"
fi

has_existing_install=0
if [[ -d "$APP_SUPPORT_DIR" || -x "$MICROMAMBA_BIN" || -d "$ENV_PREFIX" || -n "$installed_version" ]]; then
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
if [[ -n "$current_version" && "$current_version" != "$installed_version" ]]; then
  need_install=1
  install_reason="update"
fi

if [[ "$need_install" == "1" ]]; then
  install_notice="EasyALMOS is being set up for the first time.\n\nThis may take a few minutes while the private runtime is installed.\n\nThe app will work only inside this workspace on macOS:\n$WORK_DIR"
  install_success_message="EasyALMOS finished installing successfully.\n\nPlease open EasyALMOS again to start the application.\n\nWorkspace:\n$WORK_DIR"

  if [[ "$install_reason" == "update" ]]; then
    install_notice="EasyALMOS found an existing installation and needs to update its private runtime.\n\nInstalled version: ${installed_version:-unknown}\nNew version: ${current_version:-unknown}\n\nThis may take a few minutes.\n\nThe app will work only inside this workspace on macOS:\n$WORK_DIR"
    install_success_message="EasyALMOS finished updating successfully.\n\nPlease open EasyALMOS again to start the application.\n\nWorkspace:\n$WORK_DIR"
  elif [[ "$install_reason" == "repair" ]]; then
    install_notice="EasyALMOS found an existing installation, but its private runtime is incomplete or damaged.\n\nEasyALMOS will repair the private runtime now. This may take a few minutes.\n\nThe app will work only inside this workspace on macOS:\n$WORK_DIR"
    install_success_message="EasyALMOS finished repairing successfully.\n\nPlease open EasyALMOS again to start the application.\n\nWorkspace:\n$WORK_DIR"
  fi

  : >"$INSTALL_LOG"
  : >"$INSTALL_ERR_LOG"
  start_notice "$install_notice"
  log "Install reason: $install_reason"
  if ! install_runtime; then
    show_error_dialog "EasyALMOS installation failed. Check the logs in ~/Library/ApplicationSupport/EasyALMOS/logs."
    exit 1
  fi
  stop_notice
  show_info_dialog "$install_success_message"
  exit 0
fi

: >"$RUNTIME_LOG"
: >"$RUNTIME_ERR_LOG"
start_notice "EasyALMOS is opening...\n\nPlease wait.\n\nThe first launch may take a little longer.\n\nOn macOS, please work inside the EasyALMOS workspace:\n$WORK_DIR"
sleep 0.5
schedule_notice_stop "$NOTICE_PID" 6
if ! launch_easyalmos; then
  show_error_dialog "EasyALMOS could not start. Check the logs in ~/Library/ApplicationSupport/EasyALMOS/logs."
  exit 1
fi
