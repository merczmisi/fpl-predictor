def test_browser_auth_delegates_to_session():
    from fpl_draft.auth import BrowserAuth

    class DummySession:
        def __init__(self):
            self.called = False

        def _ensure_authenticated(self, entry_id=0):
            self.called = True
            return f"tok-{entry_id}"

    ds = DummySession()
    auth = BrowserAuth(ds)

    token = auth.ensure_authenticated(123)

    assert ds.called is True
    assert token == "tok-123"
