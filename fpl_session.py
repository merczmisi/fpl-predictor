from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import pandas as pd

import requests
from playwright.sync_api import (
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)


class FPLSession:
    """
    FPL API session backed by a persistent Playwright browser profile.

    Authentication architecture:

        Persistent Playwright browser
                    |
                    v
        Premier League OIDC session
                    |
                    v
             FPL getUser()
                    |
             signinSilent()
                    |
                    v
              access_token
                    |
                    v
             Python requests
                    |
                    v
                 FPL API

    The browser owns the OAuth / refresh-token lifecycle.

    Python does NOT directly use the refresh token.
    """

    DRAFT_URL = "https://draft.premierleague.com/"
    DRAFT_API_URL = "https://draft.premierleague.com"
    FANTASY_API_URL = "https://fantasy.premierleague.com"

    OIDC_PREFIX = (
        "oidc.user:https://account.premierleague.com/as:"
    )

    TOKEN_URL = (
        "https://account.premierleague.com/as/token"
    )

    ACCESS_TOKEN_SAFETY_MARGIN = 60

    TOKEN_REFRESH_TIMEOUT = 30_000
    OIDC_WRITE_TIMEOUT = 15_000
    LOGIN_TIMEOUT = 300_000

    def __init__(
        self,
        profile_dir: str | Path = "~/.fpl-playwright",
        headless: bool = True,
    ):
        self.profile_dir = Path(profile_dir).expanduser()
        self.headless = headless

        self.http = requests.Session()

        self.http.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) "
                    "Version/26.3.1 Safari/605.1.15"
                ),
            }
        )

        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

        # Python-side cache of the browser's current access token.
        self.access_token: str | None = None
        self.expires_at: float = 0

        # OAuth responses observed by Playwright.
        self._oauth_responses: list[dict[str, Any]] = []

        # Used to prevent duplicate Playwright listeners.
        self._listeners_installed = False

    # ================================================================
    # Browser lifecycle
    # ================================================================

    def start(self) -> None:
        """
        Start the persistent browser.

        If the persistent profile already contains an FPL session,
        that session is reused.
        """

        if self._context is None:

            self.profile_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            self._playwright = sync_playwright().start()

            self._context = (
                self._playwright.chromium.launch_persistent_context(
                    user_data_dir=str(self.profile_dir),
                    headless=self.headless,
                )
            )

        self._page = self._get_page()

        # Listeners MUST be installed after _page exists.
        self._install_listeners()

        # ------------------------------------------------------------
        # Navigate to FPL if we're on about:blank or elsewhere.
        # ------------------------------------------------------------

        if not self._is_fpl_page():

            print("Opening FPL...")

            try:
                self._page.goto(
                    self.DRAFT_URL,
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            except PlaywrightTimeoutError:
                # The FPL application can continue loading after
                # domcontentloaded. That's fine.
                pass

        try:
            self._page.wait_for_load_state(
                "domcontentloaded",
                timeout=10_000,
            )
        except PlaywrightTimeoutError:
            pass

    def _install_listeners(self) -> None:
        """
        Install browser traffic listeners.

        This must only run after self._page has been created.
        """

        if self._page is None:
            return

        if self._listeners_installed:
            return

        self._page.on(
            "response",
            self._on_response,
        )

        self._page.on(
            "request",
            self._on_request,
        )

        self._listeners_installed = True

    def _on_response(self, response) -> None:
        """
        Observe OAuth token responses.

        We don't need the response to refresh the token ourselves;
        this is primarily diagnostic and lets us see that the browser
        actually performed the OAuth renewal.
        """

        if response.url != self.TOKEN_URL:
            return

        print()
        print(">>> OAuth TOKEN RESPONSE")
        print("Status:", response.status)

        try:
            body = response.json()
        except Exception as exc:
            print(
                "Could not parse OAuth response:",
                exc,
            )
            return

        if not isinstance(body, dict):
            return

        if body.get("access_token"):
            self._oauth_responses.append(body)

            print("New access token received.")

            if body.get("expires_in") is not None:
                print(
                    "expires_in:",
                    body.get("expires_in"),
                )

    def _on_request(self, request) -> None:
        """
        Debug browser traffic without printing credentials.
        """

        if "/as/" in request.url:

            print(
                ">>> REQUEST:",
                request.method,
                request.url,
            )

        if "/api/entry/" in request.url:

            print()
            print("========== FPL API REQUEST ==========")
            print("METHOD:", request.method)
            print("URL:", request.url)
            print("HEADERS:")

            for name, value in request.headers.items():

                if name.lower() in {
                    "authorization",
                    "x-api-authorization",
                    "cookie",
                }:
                    print(
                        f"  {name}: <REDACTED>"
                    )
                else:
                    print(
                        f"  {name}: {value}"
                    )

            print("=====================================")

    def _get_page(self) -> Page:
        """
        Return the most useful existing page.

        Prefer an existing FPL page over about:blank.
        """

        assert self._context is not None

        pages = [
            page
            for page in self._context.pages
            if not page.is_closed()
        ]

        # Prefer FPL.
        for page in pages:

            if page.url.startswith(
                "https://draft.premierleague.com"
            ):
                return page

        # Then any non-blank page.
        for page in pages:

            if page.url != "about:blank":
                return page

        # Finally reuse the first page.
        if pages:
            return pages[0]

        return self._context.new_page()

    def close(self) -> None:
        """Close browser and Playwright."""

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

    # ================================================================
    # Page state
    # ================================================================

    def _is_fpl_page(self) -> bool:
        if self._page is None:
            return False

        try:
            return self._page.url.startswith(
                "https://draft.premierleague.com"
            )
        except Exception:
            return False

    def _is_login_page(self) -> bool:
        if self._page is None:
            return False

        try:
            return (
                "account.premierleague.com/as/authorize"
                in self._page.url
            )
        except Exception:
            return False

    # ================================================================
    # OIDC localStorage
    # ================================================================

    def _read_oidc_user(self) -> dict[str, Any] | None:
        """
        Read and parse the FPL OIDC user from localStorage.

        The localStorage value is JSON like:

            {
                "access_token": "...",
                "refresh_token": "...",
                "expires_at": 1234567890,
                ...
            }

        IMPORTANT:
        We only return the parsed object. We do not print or expose
        the refresh token.
        """

        if self._page is None:
            return None

        try:
            if not self._is_fpl_page():
                return None

            result = self._page.evaluate(
                """
                (prefix) => {

                    for (
                        let i = 0;
                        i < localStorage.length;
                        i++
                    ) {
                        const key =
                            localStorage.key(i);

                        if (
                            key &&
                            key.startsWith(prefix)
                        ) {
                            const value =
                                localStorage.getItem(key);

                            if (!value) {
                                return null;
                            }

                            try {
                                return JSON.parse(value);
                            } catch (e) {
                                return null;
                            }
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

            # Navigation may destroy the execution context.
            if (
                "Execution context was destroyed"
                in message
                or "Execution context was not found"
                in message
                or "Access is denied" in message
            ):
                return None

            return None

    def _sync_browser_token(self) -> bool:
        """
        Synchronize Python's token cache with localStorage.
        """

        user = self._read_oidc_user()

        if not user:
            return False

        access_token = user.get("access_token")

        if not access_token:
            return False

        try:
            expires_at = float(
                user.get("expires_at", 0)
            )
        except (
            TypeError,
            ValueError,
        ):
            return False

        self.access_token = access_token
        self.expires_at = expires_at

        return True

    def _token_is_valid(self) -> bool:
        """
        Return True if the cached access token has enough lifetime
        remaining.
        """

        return bool(
            self.access_token
            and time.time()
            < self.expires_at
            - self.ACCESS_TOKEN_SAFETY_MARGIN
        )

    # ================================================================
    # Browser-side authentication
    # ================================================================

    def _browser_trigger_authentication(
        self,
        entry_id: int = 299995,
    ) -> dict[str, Any]:
        """
        Make an API request from inside the FPL browser.

        This is deliberate.

        FPL monkey-patches window.fetch. Its wrapper does:

            getUser()
                |
                +-- token valid -> use it
                |
                +-- token near expiry -> signinSilent()
                |
                +-- token expired + refresh fails -> login

        Therefore calling window.fetch() causes FPL itself to run
        its normal authentication logic.

        We do NOT directly call /as/token here.
        """

        if self._page is None:
            raise RuntimeError(
                "Playwright page is not running."
            )

        if not self._is_fpl_page():

            print("Opening FPL...")

            try:
                self._page.goto(
                    self.DRAFT_URL,
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
            except PlaywrightTimeoutError:
                pass

        url = (
            f"{self.DRAFT_API_URL}"
            f"/api/entry/{entry_id}/my-team"
        )

        result = self._page.evaluate(
            """
            async (url) => {

                try {

                    const response =
                        await window.fetch(
                            url,
                            {
                                method: "GET",
                                headers: {
                                    "Accept":
                                        "application/json"
                                },
                                credentials:
                                    "include"
                            }
                        );

                    return {
                        ok: true,
                        status: response.status,
                        text:
                            await response.text()
                    };

                } catch (error) {

                    return {
                        ok: false,
                        status: 0,
                        text: String(error)
                    };
                }
            }
            """,
            url,
        )

        return result

    def _refresh_through_browser(
        self,
        entry_id: int = 299995,
    ) -> str | None:
        """
        Ask the FPL application to obtain a current access token.

        The important part is that the browser's own fetch wrapper
        invokes getUser(), and getUser() invokes signinSilent() when
        the access token needs renewal.
        """

        self.start()

        if self._page is None:
            raise RuntimeError(
                "Playwright page is not available."
            )

        # First, see whether a usable token already exists.
        if self._sync_browser_token():
            if self._token_is_valid():
                print(
                    "Browser already has a valid access token."
                )
                return self.access_token

        self._oauth_responses.clear()

        print(
            "Asking FPL browser session to refresh..."
        )

        result = self._browser_trigger_authentication(
            entry_id=entry_id,
        )

        print(
            "Browser FPL API status:",
            result.get("status"),
        )

        # ------------------------------------------------------------
        # Give signinSilent() / localStorage a short amount of time
        # to finish writing the renewed OIDC user.
        # ------------------------------------------------------------

        deadline = (
            time.time()
            + self.OIDC_WRITE_TIMEOUT / 1000
        )

        while time.time() < deadline:

            if self._sync_browser_token():

                if self._token_is_valid():

                    print(
                        "Browser access token is valid."
                    )

                    return self.access_token

            # A token endpoint response is another strong indication
            # that silent renewal completed.
            if self._oauth_responses:

                if self._sync_browser_token():

                    return self.access_token

            try:
                self._page.wait_for_timeout(250)
            except Exception:
                time.sleep(0.25)

        # ------------------------------------------------------------
        # If the API call itself succeeded, localStorage should still
        # contain the access token.
        # ------------------------------------------------------------

        if self._sync_browser_token():

            if self.access_token:

                return self.access_token

        # ------------------------------------------------------------
        # If FPL redirected to the OAuth login, silent authentication
        # failed and the persistent session is no longer sufficient.
        # ------------------------------------------------------------

        if self._is_login_page():

            raise RuntimeError(
                "FPL interactive login required."
            )

        # ------------------------------------------------------------
        # No OIDC user.
        # ------------------------------------------------------------

        raise RuntimeError(
            "FPL browser did not produce a usable "
            "OAuth access token."
        )

    # ================================================================
    # Interactive login
    # ================================================================

    def _wait_for_login(self) -> None:
        """
        Wait for an interactive login to finish.

        The browser must be visible.
        """

        if self._page is None:
            raise RuntimeError(
                "Browser page does not exist."
            )

        print()
        print("=" * 60)
        print("FPL LOGIN REQUIRED")
        print("=" * 60)
        print()
        print(
            "Complete the Premier League login "
            "in the browser."
        )
        print()
        print(
            "Waiting for redirect back to FPL..."
        )
        print()

        deadline = (
            time.time()
            + self.LOGIN_TIMEOUT / 1000
        )

        while time.time() < deadline:

            if self._is_fpl_page():

                # Let the frontend finish the OAuth code exchange.
                try:
                    self._page.wait_for_timeout(1000)
                except Exception:
                    pass

                if self._sync_browser_token():

                    if self._token_is_valid():

                        print()
                        print(
                            "Login successful."
                        )
                        print()

                        return

            time.sleep(0.5)

        raise TimeoutError(
            "Interactive FPL login did not complete "
            "within 5 minutes."
        )

    def _restart_visible_for_login(self) -> None:
        """
        Reopen the same persistent profile visibly.

        This preserves the persistent Chromium profile.
        """

        print()
        print(
            "Authentication requires interactive login."
        )
        print(
            "Opening the persistent browser visibly..."
        )
        print()

        # Close only the browser context.
        if self._context is not None:

            try:
                self._context.close()
            except Exception:
                pass

        self._context = None
        self._page = None
        self._listeners_installed = False

        if self._playwright is None:
            self._playwright = (
                sync_playwright().start()
            )

        self._context = (
            self._playwright.chromium
            .launch_persistent_context(
                user_data_dir=str(
                    self.profile_dir
                ),
                headless=False,
            )
        )

        self._page = self._get_page()

        self._install_listeners()

        try:
            self._page.goto(
                self.DRAFT_URL,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except PlaywrightTimeoutError:
            pass

        self._wait_for_login()

    # ================================================================
    # Authentication
    # ================================================================

    def _ensure_authenticated(
        self,
        entry_id: int = 299995,
    ) -> str:
        """
        Return a valid access token.

        Authentication order:

        1. Use cached/browser token if valid.
        2. Ask FPL's own fetch/getUser machinery to silently renew.
        3. If the persistent login is genuinely expired, open the
           same persistent profile visibly and request interactive login.
        """

        self.start()

        # ------------------------------------------------------------
        # Existing token.
        # ------------------------------------------------------------

        if self._sync_browser_token():

            if self._token_is_valid():
                return self.access_token

            print(
                "Access token expired/expiring."
            )

        else:

            print(
                "No usable browser access token found."
            )

        # ------------------------------------------------------------
        # Browser-side silent renewal.
        # ------------------------------------------------------------

        try:

            token = self._refresh_through_browser(
                entry_id=entry_id,
            )

            if token:
                return token

        except RuntimeError as exc:

            print(
                "Browser authentication could not "
                "silently recover:"
            )
            print(
                " ",
                str(exc),
            )

        # ------------------------------------------------------------
        # At this point we need an interactive login.
        # ------------------------------------------------------------

        if self.headless:

            self._restart_visible_for_login()

        else:

            if not self._is_fpl_page():

                try:
                    self._page.goto(
                        self.DRAFT_URL,
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                except PlaywrightTimeoutError:
                    pass

            self._wait_for_login()

        # ------------------------------------------------------------
        # Synchronize the newly authenticated user.
        # ------------------------------------------------------------

        deadline = (
            time.time()
            + self.OIDC_WRITE_TIMEOUT / 1000
        )

        while time.time() < deadline:

            if self._sync_browser_token():

                if self._token_is_valid():

                    return self.access_token

            time.sleep(0.25)

        raise RuntimeError(
            "Interactive login completed, but no valid "
            "FPL access token was found."
        )

    def _ensure_token(
        self,
        entry_id: int = 299995,
    ) -> str:
        """
        Backwards-compatible alias.
        """

        return self._ensure_authenticated(
            entry_id=entry_id,
        )

    # ================================================================
    # HTTP
    # ================================================================

    def request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> requests.Response:
        """
        Make an authenticated Python HTTP request.

        Python requests receives only the current access token.
        """

        # Extract entry ID when possible so that the browser can use
        # the same entry when it needs to trigger authentication.
        entry_id = 299995

        parts = url.split("/")

        try:
            index = parts.index("entry")
            entry_id = int(parts[index + 1])
        except (
            ValueError,
            IndexError,
        ):
            pass

        token = self._ensure_authenticated(
            entry_id=entry_id,
        )

        headers = kwargs.pop(
            "headers",
            {},
        ).copy()

        headers["X-Api-Authorization"] = (
            f"Bearer {token}"
        )

        response = self.http.request(
            method,
            url,
            headers=headers,
            **kwargs,
        )

        # ------------------------------------------------------------
        # The token can expire between our check and the actual
        # requests request.
        # ------------------------------------------------------------

        if response.status_code == 401:

            print()
            print(
                "FPL API returned 401."
            )
            print(
                "Refreshing browser authentication..."
            )

            self.access_token = None
            self.expires_at = 0

            token = self._refresh_through_browser(
                entry_id=entry_id,
            )

            if not token:
                raise RuntimeError(
                    "Browser failed to provide a new "
                    "FPL access token after a 401."
                )

            headers["X-Api-Authorization"] = (
                f"Bearer {token}"
            )

            response = self.http.request(
                method,
                url,
                headers=headers,
                **kwargs,
            )

        return response

    def get(
        self,
        url: str,
        **kwargs,
    ) -> requests.Response:

        return self.request(
            "GET",
            url,
            **kwargs,
        )

    def post(
        self,
        url: str,
        **kwargs,
    ) -> requests.Response:

        return self.request(
            "POST",
            url,
            **kwargs,
        )

    def put(
        self,
        url: str,
        **kwargs,
    ) -> requests.Response:

        return self.request(
            "PUT",
            url,
            **kwargs,
        )

    def delete(
        self,
        url: str,
        **kwargs,
    ) -> requests.Response:

        return self.request(
            "DELETE",
            url,
            **kwargs,
        )

    # ================================================================
    # FPL API
    # ================================================================

    def my_team(
        self,
        entry_id: int,
    ):
        """
        Get the current fantasy team.
        """

        url = (
            f"{self.DRAFT_API_URL}"
            f"/api/entry/{entry_id}"
            f"/my-team"
        )

        response = self.get(url)

        response.raise_for_status()

        return response.json()


    def get_player_ids(
        self,
        entry_id: int, 
        event_id: int
    ):

        url = (
            f"{self.DRAFT_API_URL}"
            f"/api/entry/{entry_id}"
            f"/event/{event_id}"
        )

        response = self.get(url)
        response.raise_for_status()

        return [pick["element"] for pick in response.json()["picks"]]

    # Get next match difficulty for each player
    def get_next_match_difficulty(
            self,
            player_id
        ):
        url = f'https://draft.premierleague.com/api/element-summary/{player_id}'
        url = (
            f"{self.DRAFT_API_URL}"
            f"/api/element-summary/{player_id}"
        )
        data = requests.get(url).json()
        
        return data['fixtures'][0]['difficulty']

    def get_bootstrap_static(self):
        """
        Get the main FPL player data.
        """
        url = (
            f"{self.FANTASY_API_URL}"
            f"/api/bootstrap-static/"
        )

        response = self.get(url)
        response.raise_for_status()
        return response.json()


    def get_expected_points(
        self,
        entry_id: int,
        event_id: int,
    ):
        """
        Calculate expected points for all players in a user's team.
        """

        # ------------------------------------------------------------
        # Get player IDs
        # ------------------------------------------------------------

        player_ids = self.get_player_ids(
            entry_id,
            event_id,
        )

        # ------------------------------------------------------------
        # Get player data
        # ------------------------------------------------------------

        data = self.get_bootstrap_static()

        players = pd.json_normalize(data["elements"])

        selected = (
            players.set_index("id")
                   .loc[player_ids]
                   .reset_index()
        )

        # ------------------------------------------------------------
        # Convert relevant columns to numbers
        # ------------------------------------------------------------

        selected["form"] = pd.to_numeric(
            selected["form"],
            errors="coerce",
        )

        selected["points_per_game"] = pd.to_numeric(
            selected["points_per_game"],
            errors="coerce",
        )

        selected["chance_of_playing_next_round"] = pd.to_numeric(
            selected["chance_of_playing_next_round"],
            errors="coerce",
        )

        # ------------------------------------------------------------
        # Calculate base points
        # ------------------------------------------------------------

        selected["base_points"] = (
            0.6 * selected["form"] +
            0.4 * selected["points_per_game"]
        )

        # ------------------------------------------------------------
        # Get next fixture difficulty
        # ------------------------------------------------------------

        selected["next_match_difficulty"] = selected["id"].apply(
            self.get_next_match_difficulty
        )

        # ------------------------------------------------------------
        # FDR multipliers
        # ------------------------------------------------------------

        fdr_multiplier = {
            1: 1.15,
            2: 1.08,
            3: 1.00,
            4: 0.92,
            5: 0.85,
        }

        selected["fdr_multiplier"] = (
            selected["next_match_difficulty"]
            .map(fdr_multiplier)
        )

        # ------------------------------------------------------------
        # Fixture-adjusted points
        # ------------------------------------------------------------

        selected["fixture_adjusted_points"] = (
            selected["base_points"] *
            selected["fdr_multiplier"]
        )

        selected["fixture_adjusted_points"] = (
            selected["fixture_adjusted_points"]
            .round(2)
        )

        # ------------------------------------------------------------
        # Expected points
        # ------------------------------------------------------------

        selected["expected_points"] = (
            selected["fixture_adjusted_points"] *
            selected["chance_of_playing_next_round"]
                .fillna(100) /
            100
        ).round(2)

        return selected