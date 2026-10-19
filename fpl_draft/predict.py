from __future__ import annotations

from typing import Any

import pandas as pd

from fpl_draft import api
from fpl_draft.features import (
    get_fixture_started,
    get_next_opponent,
    get_team_fixture_difficulty,
    rank_players_by_position,
    sum_total_points_since_event,
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
    """Return external model predictions for an entry/event."""
    player_ids = api.get_player_ids(client, entry_id, event_id)
    return _build_expected_points_dataframe(client, player_ids, event_id)


def _build_expected_points_dataframe(
    client: Any, player_ids: list[int], event_id: int
) -> pd.DataFrame:
    prediction_data = api.get_predictions(event_id)
    if prediction_data.get("gw") != event_id:
        raise ValueError(
            f"Prediction file gameweek {prediction_data.get('gw')!r} "
            f"does not match requested event {event_id}."
        )

    prediction_players = prediction_data.get("players")
    required_columns = {"id", "pred_total_points"}
    if not isinstance(prediction_players, list) or not prediction_players:
        raise ValueError(f"Prediction file for event {event_id} has no players.")
    predictions = pd.DataFrame(prediction_players)
    if not required_columns.issubset(predictions.columns):
        missing_columns = sorted(required_columns - set(predictions.columns))
        raise ValueError(
            f"Prediction file for event {event_id} is missing fields: "
            f"{', '.join(missing_columns)}."
        )

    predictions["id"] = pd.to_numeric(predictions["id"], errors="coerce")
    predictions["pred_total_points"] = pd.to_numeric(
        predictions["pred_total_points"], errors="coerce"
    )
    if (
        predictions[["id", "pred_total_points"]].isna().any().any()
        or predictions["id"].mod(1).ne(0).any()
    ):
        raise ValueError(
            f"Prediction file for event {event_id} contains invalid player IDs "
            "or predicted points."
        )
    if predictions["id"].duplicated().any():
        raise ValueError(
            f"Prediction file for event {event_id} contains duplicate player IDs."
        )
    predictions["id"] = predictions["id"].astype(int)

    missing_ids = sorted(set(player_ids) - set(predictions["id"]))
    if missing_ids:
        raise ValueError(
            f"Prediction file for event {event_id} is missing player IDs: "
            f"{', '.join(map(str, missing_ids))}."
        )

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

    future_fixtures = api.get_fixtures(client, event_id)
    selected["next_match_difficulty"] = selected["team"].apply(
        lambda team_id: get_team_fixture_difficulty(team_id, future_fixtures)
    )
    prediction_points = predictions.set_index("id")["pred_total_points"]
    selected["expected_points"] = selected["id"].map(prediction_points)

    return selected


def compute_expected_points_for_entry_from_my_team(
    client: Any,
    event_id: int,
) -> pd.DataFrame:
    """Return external model predictions for the persistent `my-team` squad."""

    entry_ids = api.get_my_entry_set(client)
    if not entry_ids:
        raise ValueError("No draft entry IDs were returned by bootstrap-dynamic.")
    entry_id = entry_ids[0]

    player_ids = api.get_my_team_ids(client, entry_id)
    return _build_expected_points_dataframe(client, player_ids, event_id)


def count_earned_points(client: Any, player_id: int, event: int) -> int:
    """Sum a player's total_points for `event` and all events after it."""
    data = api.get_element_summary(client, player_id)
    history = data.get("history") or []
    return sum_total_points_since_event(history, event)


def get_traded_players(
    client: Any,
    entry_id: int,
    event_id: int,
    league_id: int,
) -> list[dict]:
    """Return trades involving players currently on `entry_id`'s squad.

    Players from `get_player_ids` with no matching trade are omitted. Each
    result includes the name of the player traded for (`traded_with_name`),
    the trade's `response_time` (falling back to `offer_time`) as
    `traded_at`, and each player's points earned since the trade
    (`points_since_trade` / `traded_with_points_since_trade`), so callers
    can render "traded for X on <date>" details alongside how each side
    of the trade performed afterwards.
    """
    player_ids = api.get_my_team_ids(client, entry_id)
    trades = api.get_trades(client, league_id)

    data = api.get_bootstrap_static(client)
    player_names = {
        element.get("id"): element.get("web_name") for element in data.get("elements", [])
    }

    results: list[dict] = []
    for player_id in player_ids:
        # Iterate from the back (most recent first) so an older trade
        # involving the same player can't override a more recent one.
        for trade in reversed(trades):
            matched = False
            for item in trade.get("tradeitem_set", []):
                element_in = item.get("element_in")
                element_out = item.get("element_out")

                if player_id == element_in:
                    traded_with = element_out
                elif player_id == element_out:
                    traded_with = element_in
                else:
                    continue

                event = trade.get("event")
                points_since_trade = (
                    count_earned_points(client, player_id, event) if event is not None else None
                )
                traded_with_points_since_trade = (
                    count_earned_points(client, traded_with, event) if event is not None else None
                )

                results.append(
                    {
                        "player_id": player_id,
                        "traded_with": traded_with,
                        "traded_with_name": player_names.get(traded_with),
                        "event": event,
                        "traded_at": trade.get("response_time") or trade.get("offer_time"),
                        "points_since_trade": points_since_trade,
                        "traded_with_points_since_trade": traded_with_points_since_trade,
                    }
                )
                matched = True
                break

            if matched:
                break

    return results


def get_traded_players_for_my_team(
    client: Any,
    league_id: int,
    event_id: int | None = None,
) -> list[dict]:
    """Resolve the persistent `my-team` entry, then return its traded-player info."""
    entry_ids = api.get_my_entry_set(client)
    if not entry_ids:
        raise ValueError("No draft entry IDs were returned by bootstrap-dynamic.")
    entry_id = entry_ids[0]

    return get_traded_players(client, entry_id, event_id, league_id)