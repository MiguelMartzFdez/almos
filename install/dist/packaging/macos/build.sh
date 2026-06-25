#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WINDOWS_ISS="$REPO_ROOT/packaging/windows/EasyALMOS.iss"
APP_TEMPLATE="$SCRIPT_DIR/app/EasyALMOS.app"
BUILD_ROOT="$SCRIPT_DIR/.build"
APP_BUILD_DIR="$BUILD_ROOT/EasyALMOS.app"
DMG_STAGE_DIR="$BUILD_ROOT/dmg-root"
DIST_DIR="$REPO_ROOT/dist/macos"
ASSETS_DIR="$SCRIPT_DIR/assets"
ICON_SOURCE="$ASSETS_DIR/easyalmos.icns"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_command grep
require_command sed
require_command rsync
require_command hdiutil

VERSION="$(grep '^#define MyAppVersion "' "$WINDOWS_ISS" | sed -E 's/^#define MyAppVersion "(.+)"$/\1/' | head -n 1)"
if [[ -z "$VERSION" ]]; then
  echo "Could not determine EasyALMOS version from $WINDOWS_ISS" >&2
  exit 1
fi

rm -rf "$APP_BUILD_DIR" "$DMG_STAGE_DIR"
mkdir -p "$BUILD_ROOT" "$DIST_DIR"
rsync -a "$APP_TEMPLATE/" "$APP_BUILD_DIR/"

mkdir -p \
  "$APP_BUILD_DIR/Contents/MacOS" \
  "$APP_BUILD_DIR/Contents/Resources/shared" \
  "$APP_BUILD_DIR/Contents/Resources/scripts" \
  "$APP_BUILD_DIR/Contents/Resources/bootstrap"

install -m 0755 "$SCRIPT_DIR/scripts/launch_easyalmos_macos.sh" "$APP_BUILD_DIR/Contents/MacOS/EasyALMOS"
install -m 0755 "$SCRIPT_DIR/scripts/bootstrap_easyalmos_macos.sh" "$APP_BUILD_DIR/Contents/Resources/scripts/bootstrap_easyalmos_macos.sh"
install -m 0644 "$REPO_ROOT/packaging/shared/almos.yaml" "$APP_BUILD_DIR/Contents/Resources/shared/almos.yaml"
printf '%s\n' "$VERSION" > "$APP_BUILD_DIR/Contents/Resources/shared/version.txt"

if [[ -f "$ICON_SOURCE" ]]; then
  install -m 0644 "$ICON_SOURCE" "$APP_BUILD_DIR/Contents/Resources/easyalmos.icns"
else
  echo "macOS icon not found at $ICON_SOURCE; EasyALMOS.app will use the default app icon."
fi

for asset_name in micromamba-osx-64 micromamba-osx-arm64; do
  if [[ -f "$ASSETS_DIR/$asset_name" ]]; then
    install -m 0755 "$ASSETS_DIR/$asset_name" "$APP_BUILD_DIR/Contents/Resources/bootstrap/$asset_name"
  fi
done

sed -i.bak "s/__EASYALMOS_VERSION__/$VERSION/g" "$APP_BUILD_DIR/Contents/Info.plist"
rm -f "$APP_BUILD_DIR/Contents/Info.plist.bak"

mkdir -p "$DMG_STAGE_DIR"
rsync -a "$APP_BUILD_DIR/" "$DMG_STAGE_DIR/EasyALMOS.app/"
ln -s /Applications "$DMG_STAGE_DIR/Applications"

DMG_OUTPUT="$DIST_DIR/easyalmos-$VERSION.dmg"
rm -f "$DMG_OUTPUT"
hdiutil create \
  -volname "EasyALMOS" \
  -srcfolder "$DMG_STAGE_DIR" \
  -ov \
  -format UDZO \
  "$DMG_OUTPUT"

echo "macOS distributable created:"
echo "  $DMG_OUTPUT"
echo
echo "First launch behavior:"
echo "  - copies or downloads Micromamba on demand"
echo "  - creates the private runtime under ~/Library/ApplicationSupport/EasyALMOS"
echo "  - launches EasyALMOS and reuses that runtime on future launches"
