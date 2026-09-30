#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/linux"
STAGE_DIR="$SCRIPT_DIR/.build/deb-root"
DEBIAN_DIR="$STAGE_DIR/DEBIAN"
PACKAGE_NAME="easyalmos"
MICROMAMBA_ASSET="$SCRIPT_DIR/assets/micromamba-linux-64"
SHARED_VERSION_FILE="$REPO_ROOT/packaging/shared/version.txt"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command dpkg-deb
require_command install

if [[ ! -f "$SHARED_VERSION_FILE" ]]; then
  echo "Required shared version file is missing: $SHARED_VERSION_FILE" >&2
  exit 1
fi

VERSION="$(head -n 1 "$SHARED_VERSION_FILE" | tr -d '\r\n')"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine the EasyALMOS version from $SHARED_VERSION_FILE" >&2
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
Architecture: amd64
Maintainer: The Alegre Group
Depends: bash, tar
Recommends: desktop-file-utils
Description: EasyALMOS full Debian installer
 This package installs the EasyALMOS launcher, menu entry, and runtime bootstrap.
 The Conda-based environment is created on first launch in the user's profile.
EOF

install -m 0755 "$SCRIPT_DIR/scripts/easyalmos_bootstrap.sh" "$STAGE_DIR/usr/bin/easyalmos"
install -m 0755 "$MICROMAMBA_ASSET" "$STAGE_DIR/usr/lib/easyalmos/bootstrap/micromamba"
install -m 0755 "$SCRIPT_DIR/scripts/install_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/install_easyalmos.sh"
install -m 0755 "$SCRIPT_DIR/scripts/launch_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/launch_easyalmos.sh"
install -m 0755 "$SCRIPT_DIR/scripts/uninstall_easyalmos.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/uninstall_easyalmos.sh"
install -m 0755 "$SCRIPT_DIR/scripts/uninstall_easyalmos_full.sh" "$STAGE_DIR/usr/lib/easyalmos/scripts/uninstall_easyalmos_full.sh"
install -m 0644 "$REPO_ROOT/packaging/shared/launch_lock.sh" "$STAGE_DIR/usr/lib/easyalmos/shared/launch_lock.sh"
install -m 0644 "$REPO_ROOT/packaging/shared/almos.yaml" "$STAGE_DIR/usr/lib/easyalmos/shared/almos.yaml"
printf '%s\n' "$VERSION" > "$STAGE_DIR/usr/lib/easyalmos/shared/version.txt"
install -m 0644 "$REPO_ROOT/packaging/windows/assets/almos_icon.png" "$STAGE_DIR/usr/share/pixmaps/almos_icon.png"

cat > "$STAGE_DIR/usr/share/applications/easyalmos.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EasyALMOS
Comment=Launch EasyALMOS
Exec=/usr/bin/easyalmos
TryExec=/usr/bin/easyalmos
Terminal=false
Icon=/usr/share/pixmaps/almos_icon.png
Categories=Science;
Keywords=EasyALMOS;ALMOS;chemistry;science;
StartupNotify=true
StartupWMClass=EasyALMOS
NoDisplay=false
EOF

cat > "$DEBIAN_DIR/postinst" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi
EOF

cat > "$DEBIAN_DIR/postrm" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "purge" ]]; then
  if [[ -d /opt/easyalmos ]]; then
    rm -rf /opt/easyalmos
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
