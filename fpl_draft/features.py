from typing import Dict

import pandas as pd


def normalize_league_details(payload: dict) -> pd.DataFrame:
    """Convert a draft league-details payload into a tidy standings DataFrame.

    The returned rows are one per league participant for the current gameweek,
    with columns that map directly to a position-over-time chart.
    """
    league = payload.get("league") or {}
    league_entries = payload.get("league_entries") or []
    standings = payload.get("standings") or []

    if not standings and not league_entries:
        return pd.DataFrame(
            columns=[
                "league_id",
                "league_name",
                "gameweek",
                "entry_id",
                "entry_name",
                "position",
                "total",
                "points_for",
                "points_against",
            ]
        )

    entry_meta_by_internal_id = {}
    for entry in league_entries:
        public_entry_id = entry.get("entry_id")
        internal_id = entry.get("id")
        entry_name = entry.get("entry_name")

        if public_entry_id is not None:
            entry_meta_by_internal_id[int(public_entry_id)] = {
                "entry_name": entry_name,
                "entry_id": int(public_entry_id),
            }

        if internal_id is not None:
            entry_meta_by_internal_id[int(internal_id)] = {
                "entry_name": entry_name,
                "entry_id": int(public_entry_id) if public_entry_id is not None else int(internal_id),
            }

    rows = []
    gameweek = (
        league.get("current_event")
        or league.get("start_event")
        or league.get("event")
        or 1
    )

    for item in standings:
        standing_entry_id = item.get("league_entry") or item.get("entry_id")
        if standing_entry_id is None:
            continue

        standing_entry_id = int(standing_entry_id)
        entry_meta = entry_meta_by_internal_id.get(standing_entry_id) or {}

        entry_name = (
            entry_meta.get("entry_name")
            or item.get("entry_name")
            or item.get("league_entry_name")
        )
        resolved_entry_id = (
            entry_meta.get("entry_id")
            or item.get("entry_id")
            or item.get("league_entry")
            or standing_entry_id
        )

        rows.append(
            {
                "league_id": league.get("id"),
                "league_name": league.get("name"),
                "gameweek": gameweek,
                "entry_id": int(resolved_entry_id),
                "entry_name": entry_name,
                "position": item.get("rank"),
                "total": item.get("total"),
                "points_for": item.get("points_for"),
                "points_against": item.get("points_against"),
            }
        )

    df = pd.DataFrame(rows)

    required = [
        "league_id",
        "league_name",
        "gameweek",
        "entry_id",
        "entry_name",
        "position",
        "total",
        "points_for",
        "points_against",
    ]

    for col in required:
        if col not in df.columns:
            df[col] = None

    return df[required]


def compute_base_points(df: pd.DataFrame) -> pd.DataFrame:
    """Compute `base_points` = 0.6*form + 0.4*points_per_game.

    Returns a new DataFrame (the same object modified) with `base_points` column.
    """
    df["base_points"] = (
        0.6 * df["form"] + 0.4 * df["points_per_game"]
    )
    return df


def apply_fdr_multiplier(
    df: pd.DataFrame, multiplier_map: Dict[int, float] | None = None
) -> pd.DataFrame:
    """Apply fixture difficulty multiplier based on `next_match_difficulty`.

    Adds `fdr_multiplier` and `fixture_adjusted_points` (rounded to 2 decimals).
    """
    if multiplier_map is None:
        multiplier_map = {
            1: 1.15,
            2: 1.08,
            3: 1.00,
            4: 0.92,
            5: 0.85,
        }

    df["fdr_multiplier"] = df["next_match_difficulty"].map(
        lambda v: multiplier_map.get(int(v)) if pd.notna(v) else None
    )

    df["fixture_adjusted_points"] = (
        df["base_points"] * df["fdr_multiplier"]
    ).round(2)

    return df


def compute_expected_points_from_df(df: pd.DataFrame) -> pd.DataFrame:
    """Compute `expected_points` using `fixture_adjusted_points` and
    `chance_of_playing_next_round`.

    Missing `chance_of_playing_next_round` is treated as 100.
    """
    df["expected_points"] = (
        df["fixture_adjusted_points"]
        * df["chance_of_playing_next_round"].fillna(100)
        / 100
    ).round(2)

    return df
