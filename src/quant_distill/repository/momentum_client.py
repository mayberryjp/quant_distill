from __future__ import annotations

from typing import Any

import httpx


class MomentumClient:
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

    def get_latest(self, ticker: str) -> dict[str, Any] | None:
        ticker = ticker.upper()
        response = self._client.get(f"{self.base_url}/momentum/by-ticker/{ticker}", params={"limit": 1})
        if response.status_code == 404:
            return None
        response.raise_for_status()
        payload: Any = response.json()
        rows = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(rows, list) and rows:
            first = rows[0]
            return first if isinstance(first, dict) else None
        return None

    def readiness(self) -> tuple[bool, str]:
        try:
            response = self._client.get(f"{self.base_url}/ready")
            return response.status_code < 500, f"http {response.status_code}"
        except httpx.HTTPError as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self._client.close()
