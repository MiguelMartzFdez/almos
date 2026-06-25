#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${EASYALMOS_INSTALL_ROOT:-${XDG_DATA_HOME:-$HOME/.local/share}/easyalmos}"
DESKTOP_FILE="${XDG_DATA_HOME:-$HOME/.local/share}/applications/easyalmos.desktop"

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

DESKTOP_SHORTCUT_FILE="$(resolve_desktop_dir)/EasyALMOS.desktop"

rm -rf "$INSTALL_ROOT"
rm -f "$DESKTOP_FILE"
rm -f "$DESKTOP_SHORTCUT_FILE"

echo "EasyALMOS was removed from $INSTALL_ROOT"
