"""Authentication adapter for FPL browser-based auth.

This is currently a thin wrapper that delegates to an underlying
session-like object which implements `_ensure_authenticated(entry_id)`.
It allows future extraction of Playwright-specific logic into this
module without changing callers.
"""
from __future__ import annotations

from typing import Any


class BrowserAuth:
    def __init__(self, session_like: Any):
        self._session = session_like

    def ensure_authenticated(self, entry_id: int = 299995) -> str:
        return self._session._ensure_authenticated(entry_id=entry_id)

    # Backwards-compatible alias
    def ensure_token(self, entry_id: int = 299995) -> str:
        return self.ensure_authenticated(entry_id=entry_id)
