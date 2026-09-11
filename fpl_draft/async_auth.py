from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page, async_playwright


class AsyncBrowserAuth:
    OIDC_PREFIX = "oidc.user:https://account.premierleague.com/as:"
    TOKEN_URL = "https://account.premierleague.com/as/token"
    ACCESS_TOKEN_SAFETY_MARGIN = 60
    OIDC_WRITE_TIMEOUT = 15_000
    LOGIN_TIMEOUT = 300_000

    def __init__(self, profile_dir: str | Path = "~/.fpl-playwright", headless: bool = True):
        self.profile_dir = Path(profile_dir).expanduser()
        self.headless = headless
        self.access_token: str | None = None
        self.expires_at = 0.0
        self._playwright = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._oauth_responses: list[dict[str, Any]] = []

    async def close(self) -> None:
        if self._context is not None:
            await self._context.close()
        if self._playwright is not None:
            await self._playwright.stop()
        self._context = None
        self._page = None
        self._playwright = None

    async def _start(self, headless: bool) -> None:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir), headless=headless
        )
        pages = [page for page in self._context.pages if not page.is_closed()]
        self._page = next((page for page in pages if page.url.startswith("https://draft.premierleague.com")), None)
        if self._page is None:
            self._page = await self._context.new_page()
        self._page.on("response", lambda response: asyncio.create_task(self._capture_response(response)))
        if not self._page.url.startswith("https://draft.premierleague.com"):
            await self._page.goto("https://draft.premierleague.com/", wait_until="domcontentloaded", timeout=30_000)

    async def _capture_response(self, response) -> None:
        if response.url != self.TOKEN_URL:
            return
        try:
            body = await response.json()
        except Exception:
            return
        if isinstance(body, dict) and body.get("access_token"):
            self._oauth_responses.append(body)

    async def _read_oidc_user(self) -> dict | None:
        if self._page is None or not self._page.url.startswith("https://draft.premierleague.com"):
            return None
        try:
            result = await self._page.evaluate(
                """
                (prefix) => {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        if (key && key.startsWith(prefix)) {
                            const value = localStorage.getItem(key);
                            if (!value) return null;
                            try { return JSON.parse(value); } catch (e) { return null; }
                        }
                    }
                    return null;
                }
                """,
                self.OIDC_PREFIX,
            )
            return result if isinstance(result, dict) else None
        except Exception:
            return None

    async def _sync_token(self) -> bool:
        user = await self._read_oidc_user()
        if not user or not user.get("access_token"):
            return False
        try:
            expires_at = float(user.get("expires_at", 0))
        except (TypeError, ValueError):
            return False
        self.access_token = user["access_token"]
        self.expires_at = expires_at
        return True

    def _token_valid(self) -> bool:
        return bool(self.access_token and time.time() < self.expires_at - self.ACCESS_TOKEN_SAFETY_MARGIN)

    async def _trigger_refresh(self) -> None:
        if self._page is None:
            return
        await self._page.evaluate(
            """
            async () => {
                const response = await window.fetch(
                    "https://draft.premierleague.com/api/entry/299995/my-team",
                    { method: "GET", headers: { "Accept": "application/json" }, credentials: "include" }
                );
                return response.status;
            }
            """
        )

    async def _wait_for_token(self, timeout_ms: int) -> bool:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if await self._sync_token() and self._token_valid():
                return True
            await asyncio.sleep(0.25)
        return False

    async def ensure_authenticated(self) -> str:
        try:
            await self._start(self.headless)
            if await self._sync_token() and self._token_valid():
                return self.access_token
            try:
                await self._trigger_refresh()
                if await self._wait_for_token(self.OIDC_WRITE_TIMEOUT):
                    return self.access_token
            except Exception:
                pass
        finally:
            await self.close()

        await self._start(False)
        if await self._wait_for_token(self.LOGIN_TIMEOUT):
            token = self.access_token
            await self.close()
            return token
        await self.close()
        raise TimeoutError("Interactive FPL login did not complete within timeout.")
