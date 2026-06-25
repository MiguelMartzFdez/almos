#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BOOTSTRAP_SCRIPT="$APP_ROOT/Resources/scripts/bootstrap_easyalmos_macos.sh"

if [[ ! -x "$BOOTSTRAP_SCRIPT" ]]; then
  osascript -e 'display dialog "EasyALMOS is missing its bootstrap script." buttons {"OK"} default button "OK" with icon stop' >/dev/null 2>&1 || true
  exit 1
fi

exec "$BOOTSTRAP_SCRIPT"
