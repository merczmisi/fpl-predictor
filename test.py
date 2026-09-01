from fpl_session import FPLSession

fpl = FPLSession(
    profile_dir="~/.fpl-playwright",
    headless=True,
)

try:
    selected = fpl.get_expected_points(299995, 2)
    print(selected[
        [
            'id',
            'web_name',
            'expected_points',
            'team',
            'element_type',
            'form',
            'points_per_game',
            'base_points',
            'next_match_difficulty',
            'chance_of_playing_next_round',
            'fixture_adjusted_points',
        ]
    ])

    print(
        "\nTotal expected points (first 11):",
        selected['expected_points'].head(11).sum()
    )
finally:
    fpl.close()