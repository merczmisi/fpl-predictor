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

    def get(self, url, **kwargs):
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
