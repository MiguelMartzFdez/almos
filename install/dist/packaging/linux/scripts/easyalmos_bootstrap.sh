#!/usr/bin/env bash
set -euo pipefail

export EASYALMOS_SYSTEM_ROOT="${EASYALMOS_SYSTEM_ROOT:-/opt/easyalmos}"
export EASYALMOS_INSTALL_ROOT="$EASYALMOS_SYSTEM_ROOT"
export EASYALMOS_SCRIPT_ROOT="${EASYALMOS_SCRIPT_ROOT:-/usr/lib/easyalmos}"

if [[ ! -d "$EASYALMOS_SYSTEM_ROOT/envs/almos" ]]; then
  echo "EasyALMOS runtime is not installed at $EASYALMOS_SYSTEM_ROOT" >&2
  exit 1
fi

exec "$EASYALMOS_SCRIPT_ROOT/scripts/launch_easyalmos.sh"
