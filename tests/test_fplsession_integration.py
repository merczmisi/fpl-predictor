import pandas as pd


class DummyResp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._json


class DummyHttpClient:
    def __init__(self, token_expected="mock-token"):
        self.token_expected = token_expected
        self.requests = []

    def request(self, method, url, headers=None, **kwargs):
        # record a snapshot of headers
        self.requests.append((method, url, dict(headers) if headers else {}))

        # simple routing
        if url.endswith("/api/bootstrap-static/"):
            return DummyResp(200, {"elements": [
                {"id": 1, "form": "2.0", "points_per_game": "4.0", "chance_of_playing_next_round": "100", "web_name": "A", "team": 1, "element_type": 1},
                {"id": 2, "form": "1.5", "points_per_game": "2.0", "chance_of_playing_next_round": "50", "web_name": "B", "team": 2, "element_type": 2},
            ]})

        if "/api/entry/" in url and "/event/" in url:
            # return picks
            return DummyResp(200, {"picks": [{"element": 1}, {"element": 2}]})

        if "/api/element-summary/1" in url:
            return DummyResp(200, {"fixtures": [{"difficulty": 1}]})

        if "/api/element-summary/2" in url:
            return DummyResp(200, {"fixtures": [{"difficulty": 5}]})

        return DummyResp(404, {})


def test_fplsession_expected_points_integration():
    from fpl_session import FPLSession

    # Create session but replace auth and http with test doubles.
    s = FPLSession(profile_dir="~/.fpl-playwright", headless=True)

    class DummyAuth:
        def ensure_authenticated(self, entry_id=0):
            return "mock-token"

        def start(self):
            return None

        def close(self):
            return None

    s.auth = DummyAuth()
    s.http = DummyHttpClient(token_expected="mock-token")

    df = s.get_expected_points(299995, 2)

    # check columns present and expected points numeric
    assert "expected_points" in df.columns
    assert df.loc[df.id == 1, "expected_points"].iloc[0] >= 0
    assert df.loc[df.id == 2, "expected_points"].iloc[0] >= 0


def test_fplsession_get_my_team_uses_current_entry_set_when_no_id_given():
    from fpl_session import FPLSession

    class DummyAuth:
        def ensure_authenticated(self, entry_id=0):
            return "mock-token"

        def start(self):
            return None

        def close(self):
            return None

    class DummyHttpClient:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers=None, **kwargs):
            self.calls.append((method, url, headers))
            if url == "https://draft.premierleague.com/api/bootstrap-dynamic":
                return DummyResp(200, {"player": {"entry_set": [12345]}})
            if url == "https://draft.premierleague.com/api/entry/12345/my-team":
                return DummyResp(200, {"picks": [{"element": 10}]})
            return DummyResp(404, {})

    s = FPLSession(profile_dir="~/.fpl-playwright", headless=True)
    s.auth = DummyAuth()
    s.http = DummyHttpClient()

    team = s.get_my_team()

    assert team["picks"][0]["element"] == 10


def _make_expected_points_http_client(game_payload):
    class DummyHttpClient:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers=None, **kwargs):
            self.calls.append((method, url, headers))

            if url == "https://draft.premierleague.com/api/game":
                return DummyResp(200, game_payload)
            if url == "https://draft.premierleague.com/api/bootstrap-dynamic":
                return DummyResp(200, {"player": {"entry_set": [999]}})
            if url == "https://draft.premierleague.com/api/entry/999/my-team":
                return DummyResp(200, {"picks": [{"element": 1}, {"element": 2}]})
            if url == "https://draft.premierleague.com/api/bootstrap-static":
                return DummyResp(
                    200,
                    {
                        "elements": [
                            {"id": 1, "form": "5.0", "points_per_game": "3.0", "chance_of_playing_next_round": "100", "team": 1},
                            {"id": 2, "form": "2.0", "points_per_game": "1.0", "chance_of_playing_next_round": "100", "team": 2},
                        ],
                        "teams": [
                            {"id": 1, "name": "Arsenal", "code": 3},
                            {"id": 2, "name": "Chelsea", "code": 8},
                            {"id": 3, "name": "Liverpool", "code": 14},
                        ],
                    },
                )
            if url == "https://draft.premierleague.com/api/event/3/fixtures":
                return DummyResp(200, [{"team_h": 1, "team_a": 3}])
            if url == "https://draft.premierleague.com/api/event/4/fixtures":
                return DummyResp(200, [{"team_h": 2, "team_a": 1}])
            if url == "https://fantasy.premierleague.com/api/fixtures/":
                return DummyResp(200, [])
            return DummyResp(404, {})

    return DummyHttpClient()


class _DummyAuth:
    def ensure_authenticated(self, entry_id=0):
        return "mock-token"

    def start(self):
        return None

    def close(self):
        return None


def test_fplsession_get_expected_points_for_my_team_uses_current_event_when_not_finished():
    from fpl_session import FPLSession

    s = FPLSession(profile_dir="~/.fpl-playwright", headless=True)
    s.auth = _DummyAuth()
    s.http = _make_expected_points_http_client(
        {"current_event": 3, "current_event_finished": False, "next_event": 4}
    )

    df = s.get_expected_points_for_my_team()

    assert df["next_opponent"].iloc[0] == "Liverpool (H)"
    assert pd.isna(df["next_opponent"].iloc[1])


def test_fplsession_get_expected_points_for_my_team_uses_next_event_when_finished():
    from fpl_session import FPLSession

    s = FPLSession(profile_dir="~/.fpl-playwright", headless=True)
    s.auth = _DummyAuth()
    s.http = _make_expected_points_http_client(
        {"current_event": 3, "current_event_finished": True, "next_event": 4}
    )

    df = s.get_expected_points_for_my_team()

    assert list(df["next_opponent"]) == ["Chelsea (A)", "Arsenal (H)"]


def test_fplsession_refreshes_auth_after_401():
    from fpl_session import FPLSession

    class DummyAuth:
        def __init__(self):
            self.refresh_calls = []

        def ensure_authenticated(self, entry_id=0):
            return "stale-token"

        def refresh_authenticated(self, entry_id=0):
            self.refresh_calls.append(entry_id)
            return "fresh-token"

    class DummyHttpClient:
        def __init__(self):
            self.calls = []

        def request(self, method, url, headers=None, **kwargs):
            self.calls.append((method, url, dict(headers or {})))
            if len(self.calls) == 1:
                return DummyResp(401, {})
            return DummyResp(200, {"ok": True})

    session = FPLSession(profile_dir="~/.fpl-playwright", headless=True)
    session.auth = DummyAuth()
    session.http = DummyHttpClient()

    response = session.get(
        "https://draft.premierleague.com/api/entry/42/my-team"
    )

    assert response.status_code == 200
    assert session.auth.refresh_calls == [42]
    assert session.http.calls[1][2]["X-Api-Authorization"] == "Bearer fresh-token"
