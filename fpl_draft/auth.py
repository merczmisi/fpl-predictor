"""Authentication adapter for FPL browser-based auth.

This is currently a thin wrapper that delegates to an underlying
session-like object which implements `_ensure_authenticated(entry_id)`.
It allows future extraction of Playwright-specific logic into this
module without changing callers.
"""
from __future__ import annotations

from typing import Any
import time
from pathlib import Path

import requests

from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


class BrowserAuth:
    """Browser-backed authentication for FPL.

    Construction modes:
    - If `session_like` is provided, this acts as a thin adapter and
      delegates `ensure_authenticated` to `session_like._ensure_authenticated`.
    - Otherwise it manages a Playwright persistent context using
      `profile_dir` and `headless`.
    """

    OIDC_PREFIX = "oidc.user:https://account.premierleague.com/as:"
    TOKEN_URL = "https://account.premierleague.com/as/token"
    ACCESS_TOKEN_SAFETY_MARGIN = 60
    OIDC_WRITE_TIMEOUT = 15_000
    LOGIN_TIMEOUT = 300_000

    def __init__(
        self,
        session_like: Any | None = None,
        profile_dir: str | Path = "~/.fpl-playwright",
        headless: bool = True,
    ):
        self._session_like = session_like

        # If session_like provided, run in delegation mode.
        if session_like is not None:
            return

        self.profile_dir = Path(profile_dir).expanduser()
        self.headless = headless

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        self.access_token: str | None = None
        self.expires_at: float = 0

        self._oauth_responses: list[dict[str, Any]] = []
        self._listeners_installed = False

        # lightweight requests session for unauthenticated calls if needed
        self._http = requests.Session()

    # -------------------------------
    # Browser lifecycle and helpers
    # -------------------------------

    def start(self) -> None:
        if self._context is None:
            self.profile_dir.mkdir(parents=True, exist_ok=True)

            self._playwright = sync_playwright().start()

            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir), headless=self.headless
            )

        if self._page is None:
            pages = [p for p in self._context.pages if not p.is_closed()]

            for p in pages:
                if p.url.startswith("https://draft.premierleague.com"):
                    self._page = p
                    break

            if self._page is None:
                self._page = self._context.new_page()

        self._install_listeners()

        # Ensure we're on the draft page; tolerate slow loads.
        if not self._is_fpl_page():
            try:
                self._page.goto("https://draft.premierleague.com/", wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass

        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except PlaywrightTimeoutError:
            pass

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass

        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass

        self._page = None
        self._context = None
        self._playwright = None
        self._listeners_installed = False

    def _install_listeners(self) -> None:
        if self._page is None:
            return
        if self._listeners_installed:
            return

        self._page.on("response", self._on_response)
        self._page.on("request", self._on_request)

        self._listeners_installed = True

    def _on_response(self, response) -> None:
        if response.url != self.TOKEN_URL:
            return

        try:
            body = response.json()
        except Exception:
            return

        if not isinstance(body, dict):
            return

        if body.get("access_token"):
            self._oauth_responses.append(body)

    def _on_request(self, request) -> None:
        return

    def _is_fpl_page(self) -> bool:
        if self._page is None:
            return False
        try:
            return self._page.url.startswith("https://draft.premierleague.com")
        except Exception:
            return False

    def _read_oidc_user(self) -> dict | None:
        if self._page is None:
            return None

        try:
            if not self._is_fpl_page():
                return None

            result = self._page.evaluate(
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

            if isinstance(result, dict):
                return result

            return None

        except Exception as exc:
            message = str(exc)
            if (
                "Execution context was destroyed" in message
                or "Execution context was not found" in message
                or "Access is denied" in message
            ):
                return None

            return None

    def _sync_browser_token(self) -> bool:
        user = self._read_oidc_user()
        if not user:
            return False

        access_token = user.get("access_token")
        if not access_token:
            return False

        try:
            expires_at = float(user.get("expires_at", 0))
        except (TypeError, ValueError):
            return False

        self.access_token = access_token
        self.expires_at = expires_at

        return True

    def _token_is_valid(self) -> bool:
        return bool(self.access_token and time.time() < self.expires_at - self.ACCESS_TOKEN_SAFETY_MARGIN)

    # -------------------------------
    # Browser-side authentication
    # -------------------------------

    def _browser_trigger_authentication(self, entry_id: int = 299995) -> dict:
        if self._page is None:
            raise RuntimeError("Playwright page is not running.")

        if not self._is_fpl_page():
            try:
                self._page.goto("https://draft.premierleague.com/", wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                pass

        url = f"{self._page.url.split('//')[0]}"  # dummy unused

        url = f"https://draft.premierleague.com/api/entry/{entry_id}/my-team"

        result = self._page.evaluate(
            """
            async (url) => {
                try {
                    const response = await window.fetch(url, { method: "GET", headers: { "Accept": "application/json" }, credentials: "include" });
                    return { ok: true, status: response.status, text: await response.text() };
                } catch (error) {
                    return { ok: false, status: 0, text: String(error) };
                }
            }
            """,
            url,
        )

        return result

    def _refresh_through_browser(self, entry_id: int = 299995) -> str | None:
        self.start()

        if self._sync_browser_token() and self._token_is_valid():
            return self.access_token

        self._oauth_responses.clear()

        result = self._browser_trigger_authentication(entry_id=entry_id)

        deadline = time.time() + self.OIDC_WRITE_TIMEOUT / 1000

        while time.time() < deadline:
            if self._sync_browser_token() and self._token_is_valid():
                return self.access_token

            if self._oauth_responses and self._sync_browser_token():
                return self.access_token

            try:
                self._page.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)

        if self._sync_browser_token() and self.access_token:
            return self.access_token

        if self._is_login_page():
            raise RuntimeError("FPL interactive login required.")

        raise RuntimeError("FPL browser did not produce a usable OAuth access token.")

    def _is_login_page(self) -> bool:
        if self._page is None:
            return False
        try:
            return "account.premierleague.com/as/authorize" in self._page.url
        except Exception:
            return False

    def _wait_for_login(self) -> None:
        if self._page is None:
            raise RuntimeError("Browser page does not exist.")

        deadline = time.time() + self.LOGIN_TIMEOUT / 1000

        while time.time() < deadline:
            if self._is_fpl_page():
                try:
                    self._page.wait_for_timeout(1000)
                except Exception:
                    pass

                if self._sync_browser_token() and self._token_is_valid():
                    return

            time.sleep(0.5)

        raise TimeoutError("Interactive FPL login did not complete within timeout.")

    def _restart_visible_for_login(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass

        self._context = None
        self._page = None
        self._listeners_installed = False

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        self._context = self._playwright.chromium.launch_persistent_context(user_data_dir=str(self.profile_dir), headless=False)
        self._page = self._context.new_page()
        self._install_listeners()

        try:
            self._page.goto("https://draft.premierleague.com/", wait_until="domcontentloaded", timeout=30_000)
        except PlaywrightTimeoutError:
            pass

        self._wait_for_login()

    # ------------------------------------------------------------
    # Public authentication API
    # ------------------------------------------------------------

    def ensure_authenticated(self, entry_id: int = 299995) -> str:
        # Delegation mode
        if self._session_like is not None:
            return self._session_like._ensure_authenticated(entry_id=entry_id)

        # Try existing token
        if self._sync_browser_token() and self._token_is_valid():
            return self.access_token

        try:
            token = self._refresh_through_browser(entry_id=entry_id)
            if token:
                return token
        except RuntimeError:
            pass

        # Interactive login path
        if self.headless:
            self._restart_visible_for_login()
        else:
            if not self._is_fpl_page():
                try:
                    self._page.goto("https://draft.premierleague.com/", wait_until="domcontentloaded", timeout=30_000)
                except PlaywrightTimeoutError:
                    pass

            self._wait_for_login()

        deadline = time.time() + self.OIDC_WRITE_TIMEOUT / 1000
        while time.time() < deadline:
            if self._sync_browser_token() and self._token_is_valid():
                return self.access_token
            time.sleep(0.25)

        raise RuntimeError("Interactive login completed, but no valid FPL access token was found.")

    # Backwards-compatible alias
    def ensure_token(self, entry_id: int = 299995) -> str:
        return self.ensure_authenticated(entry_id=entry_id)

