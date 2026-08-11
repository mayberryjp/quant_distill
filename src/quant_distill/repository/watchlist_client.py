from __future__ import annotations

from typing import Any

import httpx


class WatchlistClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        timeout: int = 15,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def get_entries(self, ticker: str) -> list[dict[str, Any]]:
        ticker = ticker.upper()
        response = self._client.get(f"{self.base_url}/watchlist/by-ticker/{ticker}")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    def readiness(self) -> tuple[bool, str]:
        try:
            response = self._client.get(f"{self.base_url}/signal-cache/ready")
            return response.status_code < 500, f"http {response.status_code}"
        except httpx.HTTPError as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self._client.close()
