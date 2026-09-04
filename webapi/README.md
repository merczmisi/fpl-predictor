# FPL Draft Web API

Minimal FastAPI backend that exposes computed expected points from the `fpl_draft` package.

Run locally (inside the project's virtualenv):

```bash
pip install fastapi uvicorn requests
uvicorn webapi.app:app --reload --host 127.0.0.1 --port 8000
```

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
