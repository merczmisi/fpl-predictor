import pandas as pd

from fpl_draft.predict import compute_expected_points_for_entry


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
                        },
                        {
                            "id": 2,
                            "form": "2.0",
                            "points_per_game": "1.0",
                            "chance_of_playing_next_round": "100",
                        },
                    ]
                }
            )

        # Element summary -> fixtures
        if "element-summary" in url:
            pid = int(url.rstrip("/").split("/")[-1])
            difficulty = 1 if pid == 1 else 3
            return DummyResponse({"fixtures": [{"difficulty": difficulty}]})

        raise AssertionError(f"Unexpected URL: {url}")


def test_compute_expected_points_simple():
    client = DummyClient()

    df = compute_expected_points_for_entry(client, entry_id=999, event_id=4)

    assert list(df["id"]) == [1, 2]

    # expected_points: player1 -> base=4.2, fdr(1)=1.15 -> 4.83; player2 -> base=1.6
    vals = list(df["expected_points"].astype(float).round(2))
    assert vals == [4.83, 1.6]
