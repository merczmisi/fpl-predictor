class DummyResp:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")

    def json(self):
        return self._json


class DummySession:
    def __init__(self, responses):
        # responses is a list of DummyResp to return sequentially
        self._responses = list(responses)
        self.requests = []

    def request(self, method, url, headers=None, **kwargs):
        # store a snapshot of headers to avoid later mutation
        self.requests.append((method, url, dict(headers) if headers else {}))
        if not self._responses:
            return DummyResp(200, {})
        return self._responses.pop(0)


def test_fpl_http_client_retries_on_401():
    from fpl_draft.http import FplHttpClient

    calls = []

    def token_provider(entry_id):
        calls.append(entry_id)
        # return a token that encodes the call count
        return f"tok-{len(calls)}"

    # first response is 401, second is 200
    session = DummySession([DummyResp(401, {}), DummyResp(200, {"ok": True})])

    client = FplHttpClient(token_provider=token_provider, session=session)

    resp = client.get("https://draft.premierleague.com/api/entry/42/event/3")

    assert resp.status_code == 200
    # token provider should have been called twice (first attempt + retry)
    assert len(calls) == 2
    # verify headers set in requests
    assert session.requests[0][2]["X-Api-Authorization"].startswith("Bearer tok-1")
    assert session.requests[1][2]["X-Api-Authorization"].startswith("Bearer tok-2")
