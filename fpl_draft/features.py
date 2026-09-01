from typing import Dict

import pandas as pd


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
