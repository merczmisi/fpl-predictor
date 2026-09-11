#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=${1:-0.1.0}
APP_NAME="FPL Draft.app"
APP_DIR="$ROOT_DIR/dist/$APP_NAME"
DMG_PATH="$ROOT_DIR/dist/fpl-draft-$VERSION-macos-arm64.dmg"
STAGING_DIR="$ROOT_DIR/dist/dmg-staging"

cd "$ROOT_DIR"
./packaging/build-macos.sh

rm -rf "$APP_DIR" "$STAGING_DIR" "$DMG_PATH"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Frameworks" "$APP_DIR/Contents/Resources" "$STAGING_DIR"

cp packaging/Info.plist "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP_DIR/Contents/Info.plist"

# Use the standard macOS layout expected by PyInstaller's bootloader.
cp "dist/fpl-draft/fpl-draft" "$APP_DIR/Contents/MacOS/fpl-draft"
cp -R "dist/fpl-draft/_internal/." "$APP_DIR/Contents/Frameworks/"
cp -R "dist/fpl-draft/playwright-browsers" "$APP_DIR/Contents/Frameworks/"

ln -s /Applications "$STAGING_DIR/Applications"
cp -R "$APP_DIR" "$STAGING_DIR/"

hdiutil create \
  -volname "FPL Draft $VERSION" \
  -srcfolder "$STAGING_DIR" \
  -ov \
  -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGING_DIR"
echo "Built: $APP_DIR"
echo "Built: $DMG_PATH"
