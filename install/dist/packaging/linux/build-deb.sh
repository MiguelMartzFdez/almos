#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WINDOWS_ISS="$REPO_ROOT/packaging/windows/EasyALMOS.iss"
DIST_DIR="$REPO_ROOT/dist/linux"
STAGE_DIR="$SCRIPT_DIR/.build/deb-root"
DEBIAN_DIR="$STAGE_DIR/DEBIAN"
PACKAGE_NAME="easyalmos"
MICROMAMBA_ASSET="$SCRIPT_DIR/assets/micromamba-linux-64"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command dpkg-deb
require_command install
require_command grep
require_command sed

VERSION="$(grep '^#define MyAppVersion "' "$WINDOWS_ISS" | sed -E 's/^#define MyAppVersion "(.+)"$/\1/' | head -n 1)"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine EasyALMOS version from $WINDOWS_ISS" >&2
  exit 1
fi

rm -rf "$STAGE_DIR"
mkdir -p \
  "$DEBIAN_DIR" \
  "$STAGE_DIR/usr/bin" \
  "$STAGE_DIR/usr/lib/easyalmos/bootstrap" \
  "$STAGE_DIR/usr/lib/easyalmos/scripts" \
  "$STAGE_DIR/usr/lib/easyalmos/shared" \
  "$STAGE_DIR/usr/share/applications" \
  "$STAGE_DIR/usr/share/pixmaps" \
  "$DIST_DIR"

if [[ ! -f "$MICROMAMBA_ASSET" ]]; then
  echo "Micromamba asset not found: $MICROMAMBA_ASSET" >&2
  exit 1
fi

cat > "$DEBIAN_DIR/control" <<EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: science
Priority: optional
Architecture: all
Maintainer: The Alegre Group
Depends: bash, tar, curl | wget
Recommends: desktop-file-utils
Description: EasyALMOS full Debian installer
 This package installs the EasyALMOS launcher, menu entry, and full runtime.
 The Conda-based environment is created during package installation.
EOF

install -m 0755 "$SCRIPT_DIR/scripts/easyalmos_bootstrap.sh" "$STAGE_DIR/usr/bin/easyalmos"
install -m 0755 "$MICROMAMBA_ASSET" "$STAGE_DIR/usr/lib/easyalmos/bootstrap/micromamba"
install -m 0755 "$SCRIPT_DIR/scripts/install_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/install_easyalmos.sh"
install -m 0755 "$SCRIPT_DIR/scripts/install_easyalmos_system.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/install_easyalmos_system.sh"
install -m 0755 "$SCRIPT_DIR/scripts/install_desktop_shortcut_system.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/install_desktop_shortcut_system.sh"
install -m 0755 "$SCRIPT_DIR/scripts/launch_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/launch_easyalmos.sh"
install -m 0755 "$SCRIPT_DIR/scripts/uninstall_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/uninstall_easyalmos.sh"
install -m 0644 "$REPO_ROOT/packaging/shared/almos.yaml" "$STAGE_DIR/usr/lib/easyalmos/shared/almos.yaml"
install -m 0644 "$REPO_ROOT/packaging/windows/assets/almos_icon.png" "$STAGE_DIR/usr/share/pixmaps/easyalmos.png"

cat > "$STAGE_DIR/usr/share/applications/easyalmos.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EasyALMOS
Comment=Launch EasyALMOS
Exec=/usr/bin/easyalmos
TryExec=/usr/bin/easyalmos
Terminal=false
Icon=/usr/share/pixmaps/easyalmos.png
Categories=Science;
EOF

cat > "$DEBIAN_DIR/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

export EASYALMOS_SCRIPT_ROOT=/usr/lib/easyalmos
export EASYALMOS_SYSTEM_ROOT=/opt/easyalmos
export EASYALMOS_INSTALL_ROOT=/opt/easyalmos
export EASYALMOS_ENV_FILE=/usr/lib/easyalmos/shared/almos.yaml
export EASYALMOS_ICON_SOURCE=/usr/share/pixmaps/easyalmos.png
export EASYALMOS_BUNDLED_MICROMAMBA=/usr/lib/easyalmos/bootstrap/micromamba

/usr/lib/easyalmos/scripts/install_easyalmos_system.sh

TARGET_USER="${SUDO_USER:-}"
if [[ -z "$TARGET_USER" ]] && command -v logname >/dev/null 2>&1; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$TARGET_USER" ]] && getent passwd 1000 >/dev/null 2>&1; then
  TARGET_USER="$(getent passwd 1000 | cut -d: -f1)"
fi
if [[ -n "$TARGET_USER" ]] && id "$TARGET_USER" >/dev/null 2>&1; then
  /usr/lib/easyalmos/scripts/install_desktop_shortcut_system.sh "$TARGET_USER" || true
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
EOF

cat > "$DEBIAN_DIR/postrm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "purge" ]]; then
  rm -rf /opt/easyalmos
fi

TARGET_USER="${SUDO_USER:-}"
if [[ -z "$TARGET_USER" ]] && command -v logname >/dev/null 2>&1; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$TARGET_USER" ]] && getent passwd 1000 >/dev/null 2>&1; then
  TARGET_USER="$(getent passwd 1000 | cut -d: -f1)"
fi
if [[ -n "$TARGET_USER" ]] && id "$TARGET_USER" >/dev/null 2>&1; then
  USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
  if [[ -n "$USER_HOME" ]]; then
    DESKTOP_DIR="$USER_HOME/Desktop"
    if command -v runuser >/dev/null 2>&1 && command -v xdg-user-dir >/dev/null 2>&1; then
      DESKTOP_DIR="$(runuser -u "$TARGET_USER" -- xdg-user-dir DESKTOP 2>/dev/null || printf '%s\n' "$DESKTOP_DIR")"
    fi
    rm -f "$DESKTOP_DIR/EasyALMOS.desktop"
  fi
fi

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
EOF

chmod 0755 "$DEBIAN_DIR/postinst" "$DEBIAN_DIR/postrm"

OUTPUT_FILE="$DIST_DIR/${PACKAGE_NAME}-${VERSION}.deb"
dpkg-deb --build "$STAGE_DIR" "$OUTPUT_FILE"

echo "Debian package created:"
echo "  $OUTPUT_FILE"
