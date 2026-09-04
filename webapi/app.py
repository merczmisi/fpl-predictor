from __future__ import annotations

from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from fpl_draft.predict import (
    compute_expected_points_for_entry,
    compute_expected_points_for_entry_from_my_team,
)
from fpl_draft.api import get_bootstrap_dynamic_entry_set
from fpl_draft.auth import BrowserAuth
from fpl_draft.http import FplHttpClient
import os


app = FastAPI(title="FPL Draft API")

# Allow CORS from localhost dev servers (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/expected_points")
def expected_points(entry_id: int, event_id: Optional[int] = None, use_my_team: bool = False):
    """Return expected points for an entry as JSON.

    Query parameters:
    - `entry_id` (int): public entry id
    - `event_id` (int, optional): gameweek/event id. If omitted and `use_my_team` is false, the backend will default to `my-team` behaviour.
    - `use_my_team` (bool): when true, compute from the persistent `my-team` payload.
    """

    # Use a browser-backed token provider for authenticated Draft API calls.
    # In CI or dev without Playwright, set FPL_AUTH_DISABLED=1 to use an unauthenticated
    # requests.Session (may receive 403s for protected endpoints).
    auth_disabled = os.environ.get("FPL_AUTH_DISABLED") == "1"

    if auth_disabled:
        client = requests.Session()
    else:
        # Reuse a BrowserAuth instance stored on the app state to avoid restarting Playwright
        if not hasattr(app.state, "browser_auth"):
            # headless can be toggled via env FPL_HEADLESS=0
            headless = os.environ.get("FPL_HEADLESS", "1") != "0"
            app.state.browser_auth = BrowserAuth(headless=headless)

        def token_provider(eid: int) -> str:
            return app.state.browser_auth.ensure_authenticated(entry_id)

        client = FplHttpClient(token_provider=token_provider)

    try:
        if use_my_team or event_id is None:
            df = compute_expected_points_for_entry_from_my_team(client, int(entry_id))
        else:
            df = compute_expected_points_for_entry(client, int(entry_id), int(event_id))

        # Convert DataFrame to JSON-serializable records
        records = df.fillna("").to_dict(orient="records")

        return {"data": records}

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        # Surface Draft API 403s more clearly
        msg = str(exc)
        if "403" in msg or "Forbidden" in msg:
            raise HTTPException(status_code=502, detail=f"Upstream API returned 403 Forbidden: {msg}")
        raise HTTPException(status_code=500, detail=msg)


@app.get("/bootstrap_dynamic_entry_set")
def bootstrap_dynamic_entry_set(entry_id: int):
    """Fetch the Draft `bootstrap-dynamic` payload and return `player.entry_set`.

    Query parameters:
    - `entry_id` (int): public entry id used to obtain an auth token when required.
    """

    auth_disabled = os.environ.get("FPL_AUTH_DISABLED") == "1"

    if auth_disabled:
        client = requests.Session()
    else:
        if not hasattr(app.state, "browser_auth"):
            headless = os.environ.get("FPL_HEADLESS", "1") != "0"
            app.state.browser_auth = BrowserAuth(headless=headless)

        def token_provider(eid: int) -> str:
            return app.state.browser_auth.ensure_authenticated(entry_id)

        client = FplHttpClient(token_provider=token_provider)

    try:
        entry_set = get_bootstrap_dynamic_entry_set(client)

        return {"entry_set": entry_set}

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        msg = str(exc)
        if "403" in msg or "Forbidden" in msg:
            raise HTTPException(status_code=502, detail=f"Upstream API returned 403 Forbidden: {msg}")
        raise HTTPException(status_code=500, detail=msg)
