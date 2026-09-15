from __future__ import annotations

from typing import Any

import pandas as pd

from fpl_draft import api
from fpl_draft.features import (
    compute_base_points,
    apply_fdr_multiplier,
    compute_expected_points_from_df,
    get_fixture_started,
    get_next_opponent,
    rank_players_by_position,
)


def get_players_on_form_by_position(
    client: Any, position: str, n: int = 20
) -> pd.DataFrame:
    """Fetch bootstrap data and return the best players at a position."""
    data = api.get_bootstrap_static(client)
    players = pd.json_normalize(data.get("elements") or [])
    return rank_players_by_position(players, position, n=n)

def get_my_players_by_position(
    client: Any,
    entry_id: int,
) -> pd.DataFrame:
    """Fetch bootstrap data and return the best players at a position."""
    data = api.get_bootstrap_static(client)
    my_team_ids = api.get_my_team_ids(client, entry_id)
    all_players = pd.json_normalize(data.get("elements") or [])
    my_team_players = all_players[all_players["id"].isin(my_team_ids)]
    return rank_players_by_position(my_team_players, position=None, n=len(my_team_players))


def compute_expected_points_for_entry(
    client: Any, entry_id: int, event_id: int
) -> pd.DataFrame:
    """Orchestrate expected points computation for an entry/event.

    - Fetch player ids via the API wrappers (uses `client.get`).
    - Fetch `bootstrap-static` and select the players in the same order.
    - Compute base points, apply FDR multipliers, and final expected points.

    The function intentionally accepts a thin `client` object with a
    `.get(url, **kwargs)` method so it can be used with `requests.Session`,
    `FplHttpClient` wrappers, or simple test doubles.
    """

    player_ids = api.get_player_ids(client, entry_id, event_id)

    data = api.get_bootstrap_static(client)

    players = pd.json_normalize(data["elements"])
    
    fixtures = api.get_event_fixtures(client, event_id)
    
    teams = pd.json_normalize(data["teams"])

    selected = players.set_index("id").loc[player_ids].reset_index()

    team_names = teams.set_index("id")["name"].to_dict()
    team_codes = teams.set_index("id")["code"].to_dict()

    selected["next_opponent"] = selected["team"].apply(
        lambda team_id: get_next_opponent(team_id, fixtures, team_names)
    )
    selected["team_code"] = selected["team"].map(team_codes)

    # Ensure numeric columns
    selected["form"] = pd.to_numeric(selected["form"], errors="coerce")
    selected["points_per_game"] = pd.to_numeric(
        selected["points_per_game"], errors="coerce"
    )
    selected["chance_of_playing_next_round"] = pd.to_numeric(
        selected["chance_of_playing_next_round"], errors="coerce"
    )

    selected = compute_base_points(selected)

    # Retrieve next match difficulty using the API wrapper which will call
    # `client.get(...)` for element summaries. This keeps network calls
    # encapsulated and makes testing easier.
    selected["next_match_difficulty"] = selected["id"].apply(
        lambda pid: api.get_next_match_difficulty(client, int(pid))
    )

    selected = apply_fdr_multiplier(selected)

    selected = compute_expected_points_from_df(selected)

    return selected


def compute_expected_points_for_entry_from_my_team(
    client: Any, entry_id: int | None = None,
) -> pd.DataFrame:
    """Compute expected points for an entry using the persistent `my-team`.

    - Resolve the active entry when no entry ID is provided.
    - Fetch the current event from the Draft game endpoint.
    - Fetch player ids from the entry's `my-team` payload.
    - Fetch `bootstrap-static` and select the players in the same order.
    - Compute base points, apply FDR multipliers, and final expected points.
    """

    if entry_id is None:
        entry_ids = api.get_bootstrap_dynamic_entry_set(client)
        if not entry_ids:
            raise ValueError("No draft entry IDs were returned by bootstrap-dynamic.")
        entry_id = entry_ids[0]

    game = api.get_game(client)
    current_event_finished = game["current_event_finished"]
    event_id = game["next_event"] if current_event_finished else game["current_event"]

    player_ids = api.get_my_team_ids(client, entry_id)

    data = api.get_bootstrap_static(client)

    players = pd.json_normalize(data["elements"])
    fixtures = api.get_event_fixtures(client, event_id)
    teams = pd.json_normalize(data["teams"])

    selected = players.set_index("id").loc[player_ids].reset_index()

    team_names = teams.set_index("id")["name"].to_dict()
    team_codes = teams.set_index("id")["code"].to_dict()

    selected["next_opponent"] = selected["team"].apply(
        lambda team_id: get_next_opponent(team_id, fixtures, team_names)
    )
    selected["team_code"] = selected["team"].map(team_codes)

    selected["event_started"] = selected["team"].apply(
        lambda team_id: get_fixture_started(team_id, fixtures)
    )

    # Ensure numeric columns
    selected["form"] = pd.to_numeric(selected["form"], errors="coerce")
    selected["points_per_game"] = pd.to_numeric(
        selected["points_per_game"], errors="coerce"
    )
    selected["chance_of_playing_next_round"] = pd.to_numeric(
        selected["chance_of_playing_next_round"], errors="coerce"
    )

    selected = compute_base_points(selected)

    selected["next_match_difficulty"] = selected["id"].apply(
        lambda pid: api.get_next_match_difficulty(client, int(pid))
    )

    selected = apply_fdr_multiplier(selected)

    selected = compute_expected_points_from_df(selected)

    return selected