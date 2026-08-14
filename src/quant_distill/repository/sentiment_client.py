from __future__ import annotations

from typing import Any

import httpx


class SentimentClient:
    def __init__(
        self,
        *,
        url: str,
        api_key: str = "",
        timeout: int = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def deliver(
        self,
        *,
        source: str,
        source_item_id: str,
        subject_type: str,
        subject: str,
        sentiment_label: str,
        sentiment_score: float | None,
        confidence: float | None,
        horizon: str | None,
        reason: str,
        observed_at: str | None,
        metadata: dict[str, Any],
        model: str,
        prompt_version: str,
    ) -> str | None:
        response = self._client.post(
            self.url,
            json={
                "source": source,
                "idempotency_key": f"{source}:{source_item_id}:{subject}:{model}:{prompt_version}",
                "subject_type": subject_type,
                "subject": subject,
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "confidence": confidence,
                "horizon": horizon,
                "reason": reason,
                "observed_at": observed_at,
                "metadata": metadata,
            },
        )
        response.raise_for_status()
        data = response.json()
        return data.get("sentiment_id") if isinstance(data, dict) else None

    def readiness(self) -> tuple[bool, str]:
        try:
            response = self._client.get(self.url.rsplit("/", 1)[0] + "/ready")
            return response.status_code < 500, f"http {response.status_code}"
        except httpx.HTTPError as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self._client.close()
