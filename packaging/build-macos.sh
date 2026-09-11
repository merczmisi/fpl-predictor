#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

(cd frontend && npm run build)
.venv/bin/python -m playwright install chromium
.venv/bin/python -m PyInstaller --noconfirm --clean packaging/fpl-draft.spec

PLAYWRIGHT_CACHE="$HOME/Library/Caches/ms-playwright"
CHROMIUM_DIR=$(find "$PLAYWRIGHT_CACHE" -maxdepth 1 -type d -name 'chromium-*' | sort | tail -n 1)
if [ -z "$CHROMIUM_DIR" ]; then
  echo "Playwright Chromium was not found in $PLAYWRIGHT_CACHE" >&2
  exit 1
fi
mkdir -p dist/fpl-draft/playwright-browsers
cp -R "$CHROMIUM_DIR" dist/fpl-draft/playwright-browsers/

echo "Built: $ROOT_DIR/dist/fpl-draft/fpl-draft"
