#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <username>" >&2
  exit 1
fi

TARGET_USER="$1"
SYSTEM_DESKTOP_FILE="/usr/share/applications/easyalmos.desktop"

if [[ ! -f "$SYSTEM_DESKTOP_FILE" ]]; then
  exit 0
fi

USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [[ -z "$USER_HOME" || ! -d "$USER_HOME" ]]; then
  exit 0
fi

resolve_user_desktop_dir() {
  local desktop_dir=""

  if command -v runuser >/dev/null 2>&1 && command -v xdg-user-dir >/dev/null 2>&1; then
    desktop_dir="$(runuser -u "$TARGET_USER" -- xdg-user-dir DESKTOP 2>/dev/null || true)"
  fi

  if [[ -z "$desktop_dir" ]]; then
    desktop_dir="$USER_HOME/Desktop"
  fi

  printf '%s\n' "$desktop_dir"
}

DESKTOP_DIR="$(resolve_user_desktop_dir)"
if [[ -z "$DESKTOP_DIR" || ! -d "$DESKTOP_DIR" ]]; then
  exit 0
fi

DESKTOP_SHORTCUT="$DESKTOP_DIR/EasyALMOS.desktop"
install -m 0755 "$SYSTEM_DESKTOP_FILE" "$DESKTOP_SHORTCUT"
chown "$TARGET_USER":"$TARGET_USER" "$DESKTOP_SHORTCUT"
