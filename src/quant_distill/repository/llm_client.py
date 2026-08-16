from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

log = logging.getLogger("quant_distill.llm_client")


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
    if stripped.endswith("```"):
        stripped = stripped[: -len("```")]
    return stripped.strip()


def _close_truncated(text: str) -> str | None:
    """Rebuild a JSON object that was cut off mid-generation by closing open structures."""
    depth = 0
    in_string = False
    escaped = False
    last_safe: int | None = None
    stack: list[str] = []

    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append("}" if char == "{" else "]")
            depth += 1
        elif char in "}]":
            if not stack:
                return None
            stack.pop()
            depth -= 1
            if depth == 0:
                return text[: index + 1]
        elif char == "," and depth > 0:
            last_safe = index

    if not stack:
        return None
    # Drop the partial trailing element, then close every structure still open.
    truncated = text[:last_safe] if last_safe is not None else text.rstrip()
    return truncated + "".join(reversed(stack))


def _parse_json_object(content: str) -> dict[str, Any]:
    candidates = [content, _strip_fences(content)]
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end > start:
        candidates.append(content[start : end + 1])
    repaired = _close_truncated(_strip_fences(content))
    if repaired:
        candidates.append(repaired)

    for candidate in candidates:
        if not candidate or not candidate.strip():
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise ValueError(f"llm response was not valid json ({len(content)} chars)")


class OpenAICompatLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: int = 300,
        max_tokens: int = 4096,
        json_mode: bool = True,
        num_ctx: int = 16384,
        retries: int = 3,
        backoff: float = 1.0,
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
        self.retries = max(1, retries)
        self.backoff = max(0.0, backoff)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # Generation can take minutes; only the connect phase should fail fast.
        timeouts = httpx.Timeout(timeout, connect=min(10.0, float(timeout)))
        self._client = client or httpx.Client(timeout=timeouts, headers=headers)

    def _extract_content(self, payload: dict[str, Any]) -> tuple[str, str | None]:
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("llm response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("llm response missing message content")
        return content, choices[0].get("finish_reason")

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

        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            payload = self._post_with_retry(body)
            content, finish_reason = self._extract_content(payload)
            usage = payload.get("usage") or {}
            try:
                return _parse_json_object(content), usage
            except ValueError as exc:
                last_exc = exc
                if finish_reason == "length":
                    log.warning(
                        "llm response truncated at max_tokens=%s; raise LLM_MAX_TOKENS or lower "
                        "DISTILL_MAX_CHUNK_CHARS",
                        self.max_tokens,
                    )
                if attempt == self.retries:
                    break
                delay = self.backoff * (2 ** (attempt - 1))
                log.warning(
                    "llm returned unparseable json (attempt %s/%s, finish_reason=%s, %s chars); "
                    "retrying in %.1fs",
                    attempt,
                    self.retries,
                    finish_reason,
                    len(content),
                    delay,
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _post_with_retry(self, body: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self._client.post(self.chat_url, json=body)
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                last_exc = exc
                if attempt == self.retries:
                    break
                delay = self.backoff * (2 ** (attempt - 1))
                log.warning(
                    "llm request failed (attempt %s/%s): %s; retrying in %.1fs",
                    attempt,
                    self.retries,
                    type(exc).__name__,
                    delay,
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def readiness(self) -> tuple[bool, str]:
        try:
            response = self._client.get(self.chat_url.rsplit("/chat/completions", 1)[0])
            return response.status_code < 500, f"http {response.status_code}"
        except httpx.HTTPError as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self._client.close()
