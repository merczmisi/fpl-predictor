import pandas as pd

from fpl_draft.predict import (
    compute_expected_points_for_entry,
    compute_expected_points_for_entry_from_my_team,
    count_earned_points,
    get_players_on_form_by_position,
    get_traded_players,
)


class DummyResponse:
    def __init__(self, data):
        self._data = data
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


class DummyClient:
    def get(self, url, **kwargs):
        # Player picks for event
        if "/api/entry/" in url and "/event/" in url:
            return DummyResponse({"picks": [{"element": 1}, {"element": 2}]})

        # Bootstrap static
        if "bootstrap-static" in url:
            return DummyResponse(
                {
                    "elements": [
                        {
                            "id": 1,
                            "form": "5.0",
                            "points_per_game": "3.0",
                            "chance_of_playing_next_round": "100",
                            "team": 1,
                        },
                        {
                            "id": 2,
                            "form": "2.0",
                            "points_per_game": "1.0",
                            "chance_of_playing_next_round": "100",
                            "team": 2,
                        },
                    ],
                    "teams": [
                        {"id": 1, "name": "Arsenal", "code": 3},
                        {"id": 2, "name": "Chelsea", "code": 8},
                        {"id": 3, "name": "Liverpool", "code": 14},
                    ],
                }
            )

        if "event/4/fixtures" in url:
            return DummyResponse(
                [
                    {"team_h": 1, "team_a": 3},
                    {"team_h": 2, "team_a": 1},
                ]
            )

        # Future fixtures (fantasy API) -> per-team difficulty
        if url.endswith("/api/fixtures/"):
            return DummyResponse(
                [{"team_h": 1, "team_a": 2, "team_h_difficulty": 1, "team_a_difficulty": 3}]
            )

        raise AssertionError(f"Unexpected URL: {url}")


def test_compute_expected_points_simple():
    client = DummyClient()

    df = compute_expected_points_for_entry(client, entry_id=999, event_id=4)

    assert list(df["id"]) == [1, 2]
    assert list(df["next_opponent"]) == ["Liverpool (H)", "Arsenal (H)"]

    # expected_points: player1 -> base=4.2, fdr(1)=1.15 -> 4.83; player2 -> base=1.6
    vals = list(df["expected_points"].astype(float).round(2))
    assert vals == [4.83, 1.6]


def test_get_players_on_form_by_position():
    class BootstrapClient:
        def get(self, url, **kwargs):
            return DummyResponse(
                {
                    "elements": [
                        {"id": 1, "web_name": "A", "form": "2", "points_per_game": "4", "team": 1, "element_type": 2},
                        {"id": 2, "web_name": "B", "form": "8", "points_per_game": "1", "team": 2, "element_type": 3},
                    ]
                }
            )

    result = get_players_on_form_by_position(BootstrapClient(), "mid")

    assert list(result["id"]) == [2]
    assert result.loc[0, "base_points"] == 5.2


def test_compute_expected_points_for_my_team_resolves_entry_with_explicit_event():
    class MyTeamClient(DummyClient):
        def get(self, url, **kwargs):
            if url.endswith("/api/bootstrap-dynamic"):
                return DummyResponse({"player": {"entry_set": [999]}})
            if url.endswith("/api/entry/999/my-team"):
                return DummyResponse({"picks": [{"element": 1}, {"element": 2}]})
            return super().get(url, **kwargs)

    df = compute_expected_points_for_entry_from_my_team(MyTeamClient(), event_id=4)

    assert list(df["next_opponent"]) == ["Liverpool (H)", "Arsenal (H)"]


def test_get_traded_players_drops_players_without_a_trade():
    class TradesClient:
        def get(self, url, **kwargs):
            if "/api/entry/" in url and "/event/" in url:
                return DummyResponse({"picks": [{"element": 1}, {"element": 2}, {"element": 3}]})
            if "/api/draft/league/" in url and url.endswith("/trades"):
                return DummyResponse(
                    {
                        "trades": [
                            {
                                "event": 3,
                                "tradeitem_set": [{"element_in": 1, "element_out": 10}],
                            },
                            {
                                "event": 4,
                                "tradeitem_set": [{"element_in": 20, "element_out": 2}],
                            },
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    result = get_traded_players(TradesClient(), entry_id=1, event_id=5, league_id=55729)

    assert result == [
        {"player_id": 1, "traded_with": 10, "event": 3},
        {"player_id": 2, "traded_with": 20, "event": 4},
    ]


def test_count_earned_points_sums_from_given_event_onward():
    class ElementSummaryClient:
        def get(self, url, **kwargs):
            if "/api/element-summary/" in url:
                return DummyResponse(
                    {
                        "history": [
                            {"event": 1, "total_points": 8},
                            {"event": 2, "total_points": 2},
                            {"event": 3, "total_points": 5},
                        ]
                    }
                )
            raise AssertionError(f"Unexpected URL: {url}")

    assert count_earned_points(ElementSummaryClient(), player_id=277, event=2) == 7

