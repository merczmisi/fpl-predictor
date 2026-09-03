import pandas as pd

from fpl_draft.features import (
    compute_base_points,
    apply_fdr_multiplier,
    compute_expected_points_from_df,
    normalize_league_details,
)
from fpl_draft.storage import save_league_history, load_league_history


def test_normalize_league_details():
    payload = {
        "league": {"id": 55729, "name": "Test League", "current_event": 3},
        "league_entries": [
            {"entry_id": 293299, "id": 295995, "entry_name": "Alpha"},
            {"entry_id": 299263, "id": 302017, "entry_name": "Beta"},
        ],
        "standings": [
            {
                "league_entry": 295995,
                "rank": 1,
                "total": 61,
                "points_for": 90,
                "points_against": 84,
            },
            {
                "league_entry": 302017,
                "rank": 2,
                "total": 58,
                "points_for": 81,
                "points_against": 78,
            },
        ],
    }

    df = normalize_league_details(payload)

    assert list(df.columns) == [
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
    assert df.loc[df.entry_id == 293299, "position"].iloc[0] == 1
    assert df.loc[df.entry_id == 293299, "gameweek"].iloc[0] == 3
    assert df.loc[df.entry_id == 299263, "entry_name"].iloc[0] == "Beta"
    assert df.loc[df.entry_id == 293299, "points_for"].iloc[0] == 90
    assert df.loc[df.entry_id == 293299, "points_against"].iloc[0] == 84


def test_save_and_load_league_history(tmp_path):
    db_path = tmp_path / "league_history.sqlite"
    payload = {
        "league": {"id": 55729, "name": "Test League", "current_event": 3},
        "league_entries": [
            {"entry_id": 293299, "id": 295995, "entry_name": "Alpha"},
            {"entry_id": 299263, "id": 302017, "entry_name": "Beta"},
        ],
        "standings": [
            {"league_entry": 295995, "rank": 1, "total": 61, "points_for": 90, "points_against": 84},
            {"league_entry": 302017, "rank": 2, "total": 58, "points_for": 81, "points_against": 78},
        ],
    }

    df = normalize_league_details(payload)
    save_league_history(df, str(db_path))
    loaded = load_league_history(55729, str(db_path))

    assert loaded.loc[loaded.entry_id == 293299, "position"].iloc[0] == 1
    assert loaded.loc[loaded.entry_id == 293299, "entry_name"].iloc[0] == "Alpha"
    assert loaded["gameweek"].nunique() == 1
    assert set(loaded.columns) == {
        "league_id",
        "league_name",
        "gameweek",
        "entry_id",
        "entry_name",
        "position",
        "total",
        "points_for",
        "points_against",
    }


def test_feature_pipeline_simple():
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "form": 2.0,
                "points_per_game": 4.0,
                "chance_of_playing_next_round": 100,
                "next_match_difficulty": 1,
            },
            {
                "id": 2,
                "form": 1.5,
                "points_per_game": 2.0,
                "chance_of_playing_next_round": 50,
                "next_match_difficulty": 5,
            },
        ]
    )

    df = compute_base_points(df)

    # base points
    assert df.loc[df.id == 1, "base_points"].iloc[0] == 0.6 * 2.0 + 0.4 * 4.0
    assert df.loc[df.id == 2, "base_points"].iloc[0] == 0.6 * 1.5 + 0.4 * 2.0

    df = apply_fdr_multiplier(df)

    # fixture adjusted (rounded to 2 decimals)
    val1 = round((0.6 * 2.0 + 0.4 * 4.0) * 1.15, 2)
    val2 = round((0.6 * 1.5 + 0.4 * 2.0) * 0.85, 2)

    assert df.loc[df.id == 1, "fixture_adjusted_points"].iloc[0] == val1
    assert df.loc[df.id == 2, "fixture_adjusted_points"].iloc[0] == val2

    df = compute_expected_points_from_df(df)

    exp1 = val1 * 100 / 100
    exp2 = round(val2 * 50 / 100, 2)

    assert df.loc[df.id == 1, "expected_points"].iloc[0] == exp1
    assert df.loc[df.id == 2, "expected_points"].iloc[0] == exp2
