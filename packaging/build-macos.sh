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
if [ ! -d "$PLAYWRIGHT_CACHE" ]; then
  echo "Playwright Chromium was not found in $PLAYWRIGHT_CACHE" >&2
  exit 1
fi
mkdir -p dist/fpl-draft/playwright-browsers
cp -R "$PLAYWRIGHT_CACHE/." dist/fpl-draft/playwright-browsers/

echo "Built: $ROOT_DIR/dist/fpl-draft/fpl-draft"
