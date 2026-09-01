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


def get_bootstrap_static(client: Any) -> dict:
    url = f"{FANTASY_API_URL}/api/bootstrap-static/"
    response = client.get(url)
    response.raise_for_status()
    return response.json()


def get_element_summary(client: Any, player_id: int) -> dict:
    url = f"{DRAFT_API_URL}/api/element-summary/{player_id}"
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
