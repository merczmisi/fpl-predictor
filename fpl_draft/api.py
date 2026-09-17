"""Lightweight wrappers around FPL/Draft HTTP endpoints.

These functions accept a `client` object with a `.get(url, **kwargs)` method
that returns a `requests.Response`-like object with `raise_for_status()` and
`json()` methods. They are intentionally thin so they can be unit-tested
with small stubs.
"""

from __future__ import annotations
from typing import Any


DRAFT_API_URL = "https://draft.premierleague.com"
FANTASY_API_URL = "https://fantasy.premierleague.com"


def get_my_team(client: Any, entry_id: int) -> dict:
    url = f"{DRAFT_API_URL}/api/entry/{entry_id}/my-team"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_player_ids(client: Any, entry_id: int, event_id: int) -> list[int]:
    url = f"{DRAFT_API_URL}/api/entry/{entry_id}/event/{event_id}"
    response = client.get(url)
    response.raise_for_status()

    body = response.json()

    picks = body.get("picks", [])

    return [pick.get("element") for pick in picks]

def get_my_team_ids(client: Any, entry_id: int) -> list[int]:
    url = f"{DRAFT_API_URL}/api/entry/{entry_id}/my-team"
    response = client.get(url)
    response.raise_for_status()

    body = response.json()

    picks = body.get("picks", [])

    return [pick.get("element") for pick in picks]


def get_bootstrap_static(client: Any) -> dict:
    url = f"{DRAFT_API_URL}/api/bootstrap-static"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_game(client: Any) -> dict:
    """Return the current Draft game and event status."""
    url = f"{DRAFT_API_URL}/api/game"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_my_entry_set(client: Any) -> list[int]:
    """Fetch the draft `bootstrap-dynamic` payload and return `player.entry_set`.

    This is a thin wrapper so callers can unit-test against a small client stub.
    """
    url = f"{DRAFT_API_URL}/api/bootstrap-dynamic"
    response = client.get(url)
    response.raise_for_status()

    body = response.json()
    player = body.get("player") or {}

    return player.get("entry_set", [])


def get_element_summary(client: Any, player_id: int) -> dict:
    url = f"{DRAFT_API_URL}/api/element-summary/{player_id}"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_event_fixtures(client: Any, event_id: int) -> list[dict]:
    """Return the fixtures for a draft event."""
    url = f"{DRAFT_API_URL}/api/event/{event_id}/fixtures"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_next_match_difficulty(client: Any, player_id: int) -> int | None:
    """Return the difficulty of the next fixture, or None if unavailable."""
    data = get_element_summary(client, player_id)

    fixtures = data.get("fixtures") or []

    if not fixtures:
        return None

    first = fixtures[0]

    return first.get("difficulty")


def get_league_details(client: Any, league_id: int) -> dict:
    """Return the league details JSON for a draft league."""
    url = f"{DRAFT_API_URL}/api/league/{league_id}/details"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_trades(client: Any, league_id: int) -> list[dict]:
    """Return the `trades` list for a draft league."""
    url = f"{DRAFT_API_URL}/api/draft/league/{league_id}/trades"
    response = client.get(url)
    response.raise_for_status()
    return response.json().get("trades", [])


def get_future_fixtures(client: Any, event_id: int | None = None) -> list[dict]:
    """Return upcoming fixtures from the fantasy `fixtures` endpoint (`future=1`).

    If `event_id` is given, only fixtures for that gameweek are returned.
    """
    url = f"{FANTASY_API_URL}/api/fixtures/"
    params = {"future": 1}
    if event_id is not None:
        params["event"] = event_id
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()
