from __future__ import annotations

import asyncio
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from fpl_draft.predict import (
    compute_expected_points_for_entry,
    compute_expected_points_for_entry_from_my_team,
)
from fpl_draft.api import get_bootstrap_dynamic_entry_set
from fpl_draft.auth import BrowserAuth
from fpl_draft.http import FplHttpClient


logger = logging.getLogger(__name__)
browser_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fpl-browser")


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


@app.get("/auth/status")
def auth_status() -> dict:
    """Return local FPL connection state without exposing credentials."""
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return {"connected": True, "mode": "disabled"}

    browser_auth = _get_browser_auth()
    connected = bool(browser_auth.access_token and browser_auth._token_is_valid())
    return {"connected": connected, "mode": "local"}


@app.post("/auth/connect")
async def auth_connect() -> dict:
    """Open the local FPL login flow when authentication is needed."""
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return {"connected": True, "mode": "disabled"}

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(browser_executor, _get_browser_auth().ensure_authenticated)
        return {"connected": True, "mode": "local"}
    except Exception as exc:
        logger.exception("FPL connection failed")
        raise HTTPException(status_code=409, detail=str(exc))


def _get_browser_auth() -> BrowserAuth:
    if not hasattr(app.state, "browser_auth"):
        headless = os.environ.get("FPL_HEADLESS", "1") != "0"
        app.state.browser_auth = BrowserAuth(headless=headless)
    return app.state.browser_auth


def _authenticated_client():
    """Create the API client on the dedicated Playwright thread."""
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return requests.Session()

    browser_auth = _get_browser_auth()

    def token_provider(eid: int) -> str:
        return browser_auth.ensure_authenticated(eid)

    return FplHttpClient(token_provider=token_provider)


def _compute_expected_points(entry_id: Optional[int], event_id: Optional[int], use_my_team: bool):
    client = _authenticated_client()

    if use_my_team or event_id is None:
        return compute_expected_points_for_entry_from_my_team(client)
    return compute_expected_points_for_entry(client, int(entry_id), int(event_id))


def _fetch_bootstrap_dynamic_entry_set(entry_id: int):
    client = _authenticated_client()
    return get_bootstrap_dynamic_entry_set(client)


@app.get("/expected_points")
async def expected_points(entry_id: Optional[int] = None, event_id: Optional[int] = None, use_my_team: bool = False):
    """Return expected points for an entry as JSON.

    Query parameters:
    - `entry_id` (int, optional): public entry id; resolved from the authenticated user's team when omitted
    - `event_id` (int, optional): gameweek/event id. If omitted and `use_my_team` is false, the backend will default to `my-team` behaviour.
    - `use_my_team` (bool): when true, compute from the persistent `my-team` payload.
    """

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            browser_executor,
            _compute_expected_points,
            entry_id,
            event_id,
            use_my_team,
        )

        # Convert DataFrame to JSON-serializable records
        records = df.fillna("").to_dict(orient="records")

        return {"data": records}

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        # Surface Draft API 403s more clearly
        msg = str(exc)
        logger.exception("Failed to compute expected points")
        if "403" in msg or "Forbidden" in msg:
            raise HTTPException(status_code=502, detail=f"Upstream API returned 403 Forbidden: {msg}")
        raise HTTPException(status_code=500, detail=msg)


@app.get("/bootstrap_dynamic_entry_set")
async def bootstrap_dynamic_entry_set(entry_id: int):
    """Fetch the Draft `bootstrap-dynamic` payload and return `player.entry_set`.

    Query parameters:
    - `entry_id` (int): public entry id used to obtain an auth token when required.
    """

    try:
        loop = asyncio.get_running_loop()
        entry_set = await loop.run_in_executor(
            browser_executor,
            _fetch_bootstrap_dynamic_entry_set,
            entry_id,
        )

        return {"entry_set": entry_set}

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        msg = str(exc)
        logger.exception("Failed to fetch bootstrap dynamic entry set")
        if "403" in msg or "Forbidden" in msg:
            raise HTTPException(status_code=502, detail=f"Upstream API returned 403 Forbidden: {msg}")
        raise HTTPException(status_code=500, detail=msg)


if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    frontend_dist = Path(sys._MEIPASS) / "frontend" / "dist"
else:
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
