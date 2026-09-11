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
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$STAGING_DIR"

cp packaging/Info.plist "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VERSION" "$APP_DIR/Contents/Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VERSION" "$APP_DIR/Contents/Info.plist"

# Use the standard macOS layout expected by PyInstaller's bootloader.
cp "dist/fpl-draft/fpl-draft" "$APP_DIR/Contents/MacOS/fpl-draft"
cp -R "dist/fpl-draft/_internal" "$APP_DIR/Contents/Resources/_internal"
cp -R "dist/fpl-draft/playwright-browsers" "$APP_DIR/Contents/Resources/_internal/playwright-browsers"
ln -s Resources/_internal "$APP_DIR/Contents/Frameworks"

# The files moved into the app bundle after PyInstaller built them, so sign the
# completed bundle. Use a Developer ID identity for distributable releases;
# ad-hoc signing keeps local development builds internally consistent.
SIGNING_IDENTITY=${MACOS_SIGNING_IDENTITY:--}
if [ "$SIGNING_IDENTITY" = "-" ]; then
  SIGNING_EXTRA_FLAGS="--timestamp=none"
else
  SIGNING_EXTRA_FLAGS="--options runtime --timestamp"
fi

# Python package directories are data, not nested app bundles. Sign only the
# actual Mach-O files, then sign the outer app so its resource seal is valid.
find "$APP_DIR/Contents" -type f -print0 | while IFS= read -r -d '' path; do
  if file "$path" | grep -q "Mach-O"; then
    codesign --force --sign "$SIGNING_IDENTITY" $SIGNING_EXTRA_FLAGS "$path"
  fi
done
codesign --force --sign "$SIGNING_IDENTITY" $SIGNING_EXTRA_FLAGS "$APP_DIR"
codesign --verify --strict --verbose=2 "$APP_DIR"

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
