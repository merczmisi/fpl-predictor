import asyncio


def test_auth_status_reports_disabled_mode(monkeypatch):
    monkeypatch.setenv("FPL_AUTH_DISABLED", "1")

    from webapi.app import auth_status

    assert asyncio.run(auth_status()) == {"connected": True, "mode": "disabled"}


def test_auth_connect_reports_disabled_mode(monkeypatch):
    monkeypatch.setenv("FPL_AUTH_DISABLED", "1")

    from webapi.app import auth_connect

    assert asyncio.run(auth_connect()) == {"connected": True, "mode": "disabled"}
