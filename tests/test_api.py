class DummyResp:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class DummyClient:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return DummyResp(self.mapping[url])


def test_get_player_ids_and_next_difficulty():
    from fpl_draft import api

    entry_url = "https://draft.premierleague.com/api/entry/1/event/2"
    elem_url = "https://draft.premierleague.com/api/element-summary/10"

    client = DummyClient(
        {
            entry_url: {"picks": [{"element": 10}]},
            elem_url: {"fixtures": [{"difficulty": 3}]},
        }
    )

    ids = api.get_player_ids(client, 1, 2)
    assert ids == [10]

    diff = api.get_next_match_difficulty(client, 10)
    assert diff == 3


def test_get_league_details():
    from fpl_draft import api

    league_url = "https://draft.premierleague.com/api/league/55729/details"
    client = DummyClient(
        {
            league_url: {
                "league": {"id": 55729, "name": "Test League"},
                "league_entries": [{"entry_id": 1, "entry_name": "Alpha"}],
                "matches": [{"event": 1, "league_entry_1": 1, "league_entry_2": 2}],
            }
        }
    )

    league = api.get_league_details(client, 55729)

    assert league["league"]["id"] == 55729
    assert league["league_entries"][0]["entry_name"] == "Alpha"
    assert league["matches"][0]["event"] == 1


def test_get_fixtures():
    from fpl_draft import api

    fixtures_url = "https://fantasy.premierleague.com/api/fixtures/"
    client = DummyClient(
        {
            fixtures_url: [
                {
                    "id": 41,
                    "event": 5,
                    "team_h": 4,
                    "team_a": 6,
                    "team_h_difficulty": 4,
                    "team_a_difficulty": 3,
                }
            ]
        }
    )

    fixtures = api.get_future_fixtures(client, event_id=5)

    assert fixtures[0]["id"] == 41
    assert fixtures[0]["team_h"] == 4
    assert client.calls == [(fixtures_url, {"params": {"future": 1, "event": 5}})]



def test_get_bootstrap_dynamic_entry_set():
    from fpl_draft import api

    url = "https://draft.premierleague.com/api/bootstrap-dynamic"
    client = DummyClient({url: {"player": {"entry_set": [299995]}}})

    entry_set = api.get_my_entry_set(client)

    assert entry_set == [299995]


def test_get_game():
    from fpl_draft import api

    url = "https://draft.premierleague.com/api/game"
    game = {
        "current_event": 3,
        "current_event_finished": False,
        "next_event": 4,
        "processing_status": "n",
        "trades_time_for_approval": True,
        "waivers_processed": False,
    }
    client = DummyClient({url: game})

    result = api.get_game(client)

    assert result == game


def test_get_event_fixtures():
    from fpl_draft import api

    url = "https://draft.premierleague.com/api/event/3/fixtures"
    fixtures = [
        {
            "id": 29,
            "event": 3,
            "team_a": 6,
            "team_h": 1,
            "kickoff_time": "2026-09-06T15:30:00Z",
        }
    ]
    client = DummyClient({url: fixtures})

    result = api.get_event_fixtures(client, 3)

    assert result == fixtures
