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

Then open `http://127.0.0.1:8000`. Select **Connect FPL account** and complete the
FPL login in the browser window opened by Playwright. The browser profile is stored
in `~/.fpl-playwright` by default, so later launches can reuse the local session.

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Example request:

```bash
curl "http://127.0.0.1:8000/expected_points?entry_id=293299&use_my_team=true"
```

Notes:
- CORS is permissive for local development. Tighten in production.
- The endpoint calls public FPL/Draft APIs; consider caching requests and adding rate-limit handling for production.
- `/auth/status` reports whether the local FPL session is currently usable.
- `/auth/connect` starts the local browser login flow without returning the token to the frontend.
- The Vite development server proxies these local API routes to port 8000.
