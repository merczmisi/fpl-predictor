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
mkdir -p "$APP_DIR/Contents/Frameworks"
for resource in "$APP_DIR/Contents/Resources/_internal/"*; do
  ln -s "../Resources/_internal/$(basename "$resource")" \
    "$APP_DIR/Contents/Frameworks/$(basename "$resource")"
done

# The files moved into the app bundle after PyInstaller built them, so sign the
# completed bundle. Use a Developer ID identity for distributable releases;
# ad-hoc signing keeps local development builds internally consistent.
SIGNING_IDENTITY=${MACOS_SIGNING_IDENTITY:--}
if [ "$SIGNING_IDENTITY" = "-" ]; then
  SIGNING_EXTRA_FLAGS="--timestamp=none"
else
  SIGNING_EXTRA_FLAGS="--options runtime --timestamp"
fi

CHROMIUM_ENTITLEMENTS="$ROOT_DIR/packaging/chromium-entitlements.plist"
PLAYWRIGHT_DIR="$APP_DIR/Contents/Resources/_internal/playwright-browsers"

sign_bundle() {
  bundle="$1"
  entitlements_args=""
  case "$bundle" in
    "$PLAYWRIGHT_DIR"/*)
      # Chromium needs hardened-runtime exceptions (JIT, unsigned exec memory, etc).
      entitlements_args="--entitlements $CHROMIUM_ENTITLEMENTS"
      ;;
  esac
  codesign --force --sign "$SIGNING_IDENTITY" $SIGNING_EXTRA_FLAGS $entitlements_args "$bundle"
}

# The playwright Chromium payload embeds nested code (Chromium.app, its
# Contents/Frameworks/*.framework, and Chromium Helper*.app variants), and
# PyInstaller may embed a Python.framework too. Apple requires signing nested
# code inside-out: `find -depth` visits a bundle's contents before the bundle
# itself, so this signs frameworks/helpers before the app that embeds them.
find "$APP_DIR/Contents" -depth \( -name "*.app" -o -name "*.framework" \) -print0 |
  while IFS= read -r -d '' bundle; do
    sign_bundle "$bundle"
  done

# Loose Mach-O binaries living outside any bundle (e.g. helper executables,
# dylibs) still need direct signatures. Skip bundle contents here since they
# were already sealed above; re-signing files inside them would break the seal.
find "$APP_DIR/Contents" \( -name "*.app" -o -name "*.framework" \) -prune -o -type f -print0 |
  while IFS= read -r -d '' path; do
    if file "$path" | grep -q "Mach-O"; then
      codesign --force --sign "$SIGNING_IDENTITY" $SIGNING_EXTRA_FLAGS "$path"
    fi
  done

codesign --force --sign "$SIGNING_IDENTITY" $SIGNING_EXTRA_FLAGS "$APP_DIR"
codesign --verify --deep --strict --verbose=2 "$APP_DIR"

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
