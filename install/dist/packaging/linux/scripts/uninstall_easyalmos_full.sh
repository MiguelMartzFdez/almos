#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="${EASYALMOS_SCRIPT_ROOT:-/usr/lib/easyalmos}"
PACKAGE_NAME="${EASYALMOS_PACKAGE_NAME:-easyalmos}"

"$SCRIPT_ROOT/scripts/uninstall_easyalmos.sh"

if ! command -v dpkg-query >/dev/null 2>&1; then
  echo "Could not verify whether $PACKAGE_NAME is installed."
  exit 1
fi

if ! dpkg-query -W -f='${Status}' "$PACKAGE_NAME" 2>/dev/null | grep -q "install ok installed"; then
  echo "$PACKAGE_NAME is not installed as a system package anymore."
  exit 0
fi

ROOT_HELPER="$(mktemp "${TMPDIR:-/tmp}/easyalmos-uninstall-root.XXXXXX.sh")"
cat >"$ROOT_HELPER" <<EOF
#!/usr/bin/env bash
set -euo pipefail

PACKAGE_NAME="$PACKAGE_NAME"
ROOT_HELPER_PATH="$ROOT_HELPER"

cleanup() {
  rm -f "\$ROOT_HELPER_PATH"
}
trap cleanup EXIT

if command -v apt-get >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get remove -y "\$PACKAGE_NAME"
else
  dpkg -r "\$PACKAGE_NAME"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
EOF
chmod 0755 "$ROOT_HELPER"

if [[ "$(id -u)" -eq 0 ]]; then
  exec "$ROOT_HELPER"
fi

if [[ -n "${DISPLAY:-}" || -n "${WAYLAND_DISPLAY:-}" ]] && command -v pkexec >/dev/null 2>&1; then
  exec pkexec "$ROOT_HELPER"
fi

if command -v sudo >/dev/null 2>&1; then
  exec sudo "$ROOT_HELPER"
fi

echo "EasyALMOS user data was removed, but the system package is still installed."
echo "Run one of these commands to remove the launcher and search entry:"
echo "  sudo apt remove $PACKAGE_NAME"
echo "  sudo dpkg -r $PACKAGE_NAME"
exit 1
