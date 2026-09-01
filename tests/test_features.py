import pandas as pd

from fpl_draft.features import (
    compute_base_points,
    apply_fdr_multiplier,
    compute_expected_points_from_df,
)


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
