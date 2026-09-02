from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
import pandas as pd

import requests
from fpl_draft.features import (
    compute_base_points,
    apply_fdr_multiplier,
    compute_expected_points_from_df,
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

        # Use a wrapper HTTP client that injects tokens via a token provider.
        from fpl_draft.http import FplHttpClient
        from fpl_draft.auth import BrowserAuth

        session = requests.Session()

        session.headers.update(
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

        # Create an auth adapter which manages browser-based tokens.
        self.auth = BrowserAuth(
            session_like=None,
            profile_dir=self.profile_dir,
            headless=self.headless,
        )

        self.http = FplHttpClient(
            token_provider=self.auth.ensure_authenticated,
            session=session,
        )

    # ================================================================
    # Browser lifecycle
    # ================================================================

    def start(self) -> None:
        return self.auth.start()

    def close(self) -> None:
        # Close auth-managed browser if present.
        try:
            self.auth.close()
        except Exception:
            pass

    def _ensure_authenticated(self, entry_id: int = 299995) -> str:
        return self.auth.ensure_authenticated(entry_id=entry_id)

    def _ensure_token(self, entry_id: int = 299995) -> str:
        return self._ensure_authenticated(entry_id=entry_id)

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
        event_id: int,
    ):
        return (
            __import__("fpl_draft.api", fromlist=["get_player_ids"])  # lazy import
            .get_player_ids(self, entry_id, event_id)
        )

    def get_my_team(
        self,
        entry_id: int
    ):
        return (
            __import__("fpl_draft.api", fromlist=["get_my_team"])  # lazy import
            .get_my_team(self, entry_id)
        )

    # Get next match difficulty for each player
    def get_next_match_difficulty(
        self,
        player_id: int,
    ):
        # Delegate to API wrapper which uses the `self` client's `.get`.
        return (
            __import__("fpl_draft.api", fromlist=["get_next_match_difficulty"])  # lazy import
            .get_next_match_difficulty(self, player_id)
        )

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
        # Get player IDs for the event
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
        # Calculate base points + fixture adjustments + expected points
        # (extracted into pure functions for testability)
        # ------------------------------------------------------------

        selected = compute_base_points(selected)

        selected["next_match_difficulty"] = selected["id"].apply(
            self.get_next_match_difficulty
        )

        selected = apply_fdr_multiplier(selected)

        selected = compute_expected_points_from_df(selected)

        return selected