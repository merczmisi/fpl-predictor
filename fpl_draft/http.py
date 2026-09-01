from __future__ import annotations

from typing import Callable, Any
import requests


class FplHttpClient:
    """HTTP client that injects FPL API authorization using a token provider.

    The token_provider callable receives an entry_id (int) and returns a
    bearer token string. The client wraps a requests-like session object.
    """

    def __init__(self, token_provider: Callable[[int], str], session: Any | None = None):
        self._token_provider = token_provider
        self._session = session or requests.Session()

    def request(self, method: str, url: str, **kwargs) -> Any:
        # Extract entry ID when possible
        entry_id = 299995

        parts = url.split("/")

        try:
            index = parts.index("entry")
            entry_id = int(parts[index + 1])
        except (ValueError, IndexError):
            pass

        token = self._token_provider(entry_id)

        headers = kwargs.pop("headers", {}).copy()
        headers["X-Api-Authorization"] = f"Bearer {token}"

        response = self._session.request(method, url, headers=headers, **kwargs)

        # If token expired, ask token provider again and retry once.
        if getattr(response, "status_code", None) == 401:
            token = self._token_provider(entry_id)
            headers["X-Api-Authorization"] = f"Bearer {token}"
            response = self._session.request(method, url, headers=headers, **kwargs)

        return response

    def get(self, url: str, **kwargs) -> Any:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> Any:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs) -> Any:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs) -> Any:
        return self.request("DELETE", url, **kwargs)
