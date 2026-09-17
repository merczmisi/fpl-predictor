from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import threading
import time
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
from fpl_draft.api import get_game, get_my_entry_set, get_league_details
from fpl_draft.auth import BrowserAuth
from fpl_draft.http import FplHttpClient
from webapi.launcher import get_auth_status, get_auth_token


logger = logging.getLogger(__name__)
browser_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fpl-browser")

_ACCESS_TOKEN_SAFETY_MARGIN = 60
_DEFAULT_TOKEN_TTL = 300  # fallback when the JWT `exp` claim can't be decoded
_TOKEN_CACHE_PATH = Path("~/.fpl/token_cache.json").expanduser()


def _decode_jwt_expiry(token: str) -> Optional[float]:
    """Best-effort extraction of the `exp` claim from a JWT access token."""
    try:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        return float(payload["exp"])
    except Exception:
        return None


def _load_disk_token_cache() -> tuple[Optional[str], float]:
    try:
        data = json.loads(_TOKEN_CACHE_PATH.read_text())
        return data.get("access_token"), float(data.get("expires_at", 0))
    except Exception:
        return None, 0.0


def _save_disk_token_cache(token: str, expires_at: float) -> None:
    # Best-effort: a stale/missing cache just means the next call re-authenticates.
    try:
        _TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _TOKEN_CACHE_PATH.with_suffix(".tmp")
        tmp_path.write_text(json.dumps({"access_token": token, "expires_at": expires_at}))
        tmp_path.chmod(0o600)
        tmp_path.replace(_TOKEN_CACHE_PATH)
    except Exception:
        logger.warning("Failed to persist FPL auth token cache", exc_info=True)


def _clear_disk_token_cache() -> None:
    try:
        _TOKEN_CACHE_PATH.unlink(missing_ok=True)
    except Exception:
        pass


class _CachedTokenProvider:
    """Caches the FPL access token, refreshing only on expiry or an explicit invalidate.

    `get_auth_token()` spawns a subprocess that launches a fresh Playwright/Chromium
    context, so it must not be called on every outgoing API request. The resolved
    token is also persisted to disk so a server restart reuses it instead of
    relaunching the browser, as long as it hasn't actually expired.
    """

    def __init__(self, fetch_token):
        self._fetch_token = fetch_token
        self._token: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def __call__(self, entry_id: int) -> str:
        with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token

            if self._token is None:
                disk_token, disk_expires_at = _load_disk_token_cache()
                if disk_token and time.time() < disk_expires_at:
                    self._token = disk_token
                    self._expires_at = disk_expires_at
                    return self._token

            return self._refresh_locked()

    def invalidate(self) -> None:
        with self._lock:
            self._token = None
            self._expires_at = 0.0
            _clear_disk_token_cache()

    def _refresh_locked(self) -> str:
        token = self._fetch_token()
        expiry = _decode_jwt_expiry(token)
        self._expires_at = (
            expiry - _ACCESS_TOKEN_SAFETY_MARGIN if expiry else time.time() + _DEFAULT_TOKEN_TTL
        )
        self._token = token
        _save_disk_token_cache(token, self._expires_at)
        return token


_token_cache = _CachedTokenProvider(get_auth_token)


app = FastAPI(title="FPL Draft API")

# Allow CORS from localhost dev servers (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


_instance_token = os.environ.get("FPL_INSTANCE_TOKEN", "unknown")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "instance": _instance_token}


def _auth_status() -> dict:
    """Return local FPL connection state without exposing credentials.

    Non-interactive: only validates an existing profile token and never
    opens a visible browser or waits on the login flow.
    """
    try:
        token = get_auth_status()
    except Exception:
        return {"connected": False, "mode": "local"}
    return {"connected": bool(token), "mode": "local"}


@app.get("/auth/status")
async def auth_status() -> dict:
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return {"connected": True, "mode": "disabled"}

    return await asyncio.to_thread(_auth_status)


@app.post("/auth/connect")
async def auth_connect() -> dict:
    """Open the local FPL login flow when authentication is needed."""
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return {"connected": True, "mode": "disabled"}

    try:
        await asyncio.to_thread(get_auth_token)
        return {"connected": True, "mode": "local"}
    except Exception as exc:
        logger.exception("FPL connection failed")
        raise HTTPException(status_code=409, detail=str(exc))


def _get_browser_auth() -> BrowserAuth:
    headless = os.environ.get("FPL_HEADLESS", "1") != "0"
    return BrowserAuth(headless=headless)


def _authenticated_client():
    """Create the API client, reusing a cached auth token across calls."""
    if os.environ.get("FPL_AUTH_DISABLED") == "1":
        return requests.Session()

    return FplHttpClient(token_provider=_token_cache)


def _compute_expected_points_my_team(event_id: int):
    client = _authenticated_client()
    return compute_expected_points_for_entry_from_my_team(client, event_id)


def _compute_expected_points(entry_id: int, event_id: Optional[int]):
    client = _authenticated_client()

    if event_id is None:
        game = get_game(client)
        event_id = game["next_event"] if game["current_event_finished"] else game["current_event"]

    return compute_expected_points_for_entry(client, entry_id, int(event_id))


def _fetch_bootstrap_dynamic_entry_set(entry_id: int):
    client = _authenticated_client()
    return get_my_entry_set(client)


def _fetch_league_details(league_id: int):
    client = _authenticated_client()
    return get_league_details(client, league_id)


def _fetch_game_state():
    client = _authenticated_client()
    return get_game(client)


@app.get("/game_state")
async def game_state():
    """Return the Draft game/event status so callers can resolve the active event id."""

    try:
        loop = asyncio.get_running_loop()
        game = await loop.run_in_executor(browser_executor, _fetch_game_state)

        return {
            "current_event": game.get("current_event"),
            "next_event": game.get("next_event"),
            "current_event_finished": game.get("current_event_finished"),
        }

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        msg = str(exc)
        logger.exception("Failed to fetch game state")
        if "403" in msg or "Forbidden" in msg:
            raise HTTPException(status_code=502, detail=f"Upstream API returned 403 Forbidden: {msg}")
        raise HTTPException(status_code=500, detail=msg)


@app.get("/expected_points/my_team")
async def expected_points_my_team(event_id: int):
    """Return expected points computed from the persistent `my-team` payload.

    Query parameters:
    - `event_id` (int): the gameweek/event id to compute expected points for.
    """

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            browser_executor,
            _compute_expected_points_my_team,
            event_id,
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


@app.get("/expected_points")
async def expected_points(entry_id: int, event_id: Optional[int] = None):
    """Return expected points for an entry as JSON.

    Query parameters:
    - `entry_id` (int): public entry id
    - `event_id` (int, optional): gameweek/event id. Defaults to the active gameweek when omitted.
    """

    try:
        loop = asyncio.get_running_loop()
        df = await loop.run_in_executor(
            browser_executor,
            _compute_expected_points,
            entry_id,
            event_id,
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


@app.get("/league/details")
async def league_details(league_id: int):
    """Return league standings/entries for a draft league id.

    Query parameters:
    - `league_id` (int): draft league id.
    """

    try:
        loop = asyncio.get_running_loop()
        payload = await loop.run_in_executor(
            browser_executor,
            _fetch_league_details,
            league_id,
        )

        return payload

    except Exception as exc:  # pragma: no cover - surface server errors as 500
        msg = str(exc)
        logger.exception("Failed to fetch league details")
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
