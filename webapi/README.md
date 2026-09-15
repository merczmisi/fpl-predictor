# FPL Draft Web API

Minimal FastAPI backend that exposes computed expected points from the `fpl_draft` package.

Run locally (inside the project's virtualenv):

```bash
pip install fastapi uvicorn requests
uvicorn webapi.app:app --reload --host 127.0.0.1 --port 8000
```

For the local companion workflow, build the frontend first:

```bash
cd frontend
npm install
npm run build
cd ..
uvicorn webapi.app:app --host 127.0.0.1 --port 8000
```

After installing the project in editable mode, the same workflow can be started
with one command. It opens the dashboard in the default browser automatically:

```bash
pip install -e .
fpl-draft
```

Use `fpl-draft --no-browser` when the dashboard should start without opening a tab.

To create a friend-facing macOS app and disk image:

```bash
./packaging/build-dmg.sh 0.1.0
```

Give friends `dist/fpl-draft-0.1.0-macos-arm64.dmg`. They open it and drag
**FPL Draft.app** into **Applications**. Their FPL login remains in
`~/.fpl-playwright` when they install a newer app version.

The default build uses an ad-hoc signature for local testing. For a build that
can be distributed without Gatekeeper warnings, use an Apple Developer ID
certificate and notarize the DMG:

```bash
security find-identity -v -p codesigning
MACOS_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)" \
	./packaging/build-dmg.sh 0.1.0
xcrun notarytool submit dist/fpl-draft-0.1.0-macos-arm64.dmg \
	--keychain-profile YOUR_NOTARY_PROFILE --wait
xcrun stapler staple dist/fpl-draft-0.1.0-macos-arm64.dmg
```

Without signing and notarization, macOS may report a downloaded app as
damaged. For a private test build on another Mac, remove the quarantine flag
after downloading:

```bash
xattr -dr com.apple.quarantine "/Applications/FPL Draft.app"
```

Then open `http://127.0.0.1:8000`. Select **Connect FPL account** and complete the
FPL login in the browser window opened by Playwright. The browser profile is stored
in `~/.fpl-playwright` by default, so later launches can reuse the local session.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Example requests:

```bash
curl "http://127.0.0.1:8000/game_state"
curl "http://127.0.0.1:8000/expected_points/my_team?event_id=4"
curl "http://127.0.0.1:8000/expected_points?entry_id=293299"
```

Notes:
- CORS is permissive for local development. Tighten in production.
- The endpoint calls public FPL/Draft APIs; consider caching requests and adding rate-limit handling for production.
- `/auth/status` reports whether the local FPL session is currently usable.
- `/auth/connect` starts the local browser login flow without returning the token to the frontend.
- The Vite development server proxies these local API routes to port 8000.
