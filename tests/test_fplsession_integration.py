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
