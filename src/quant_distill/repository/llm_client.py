from __future__ import annotations

import json
from typing import Any

import httpx


class OpenAICompatLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: int = 60,
        max_tokens: int = 4096,
        json_mode: bool = True,
        num_ctx: int = 16384,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Accept either the API root (.../v1) or the full chat completions endpoint.
        self.chat_url = (
            self.base_url
            if self.base_url.endswith("/chat/completions")
            else f"{self.base_url}/chat/completions"
        )
        self.model = model
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.num_ctx = num_ctx
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = client or httpx.Client(timeout=timeout, headers=headers)

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("llm response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("llm response missing message content")
        return content

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "stream": False,
            "options": {"num_ctx": self.num_ctx},
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        response = self._client.post(self.chat_url, json=body)
        response.raise_for_status()
        payload = response.json()
        content = self._extract_content(payload)
        usage = payload.get("usage") or {}
        return json.loads(content), usage

    def readiness(self) -> tuple[bool, str]:
        try:
            response = self._client.get(self.chat_url.rsplit("/chat/completions", 1)[0])
            return response.status_code < 500, f"http {response.status_code}"
        except httpx.HTTPError as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self._client.close()
