from __future__ import annotations

import httpx
import pytest

from quant_distill.repository.llm_client import OpenAICompatLLMClient, _parse_json_object


def _client(responses: list[str], **kwargs: object) -> OpenAICompatLLMClient:
    remaining = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        content = remaining.pop(0)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 5},
            },
        )

    transport = httpx.MockTransport(handler)
    return OpenAICompatLLMClient(
        base_url="http://llm/v1",
        model="test",
        backoff=0.0,
        client=httpx.Client(transport=transport),
        **kwargs,  # type: ignore[arg-type]
    )


def test_parses_fenced_json() -> None:
    assert _parse_json_object('```json\n{"summary": "hi"}\n```') == {"summary": "hi"}


def test_parses_json_with_surrounding_prose() -> None:
    assert _parse_json_object('Sure!\n{"summary": "hi"}\nHope that helps.') == {"summary": "hi"}


def test_repairs_truncated_json() -> None:
    truncated = '{"summary": "hi", "key_topics": ["a", "b"], "segments": [{"speaker": "Host", "sum'
    assert _parse_json_object(truncated) == {
        "summary": "hi",
        "key_topics": ["a", "b"],
        "segments": [{"speaker": "Host"}],
    }


def test_rejects_unsalvageable_content() -> None:
    with pytest.raises(ValueError):
        _parse_json_object("not json at all")


def test_complete_json_retries_on_bad_json() -> None:
    client = _client(["}{ broken", '{"summary": "ok"}'], retries=2)
    data, usage = client.complete_json("system", "user")
    assert data == {"summary": "ok"}
    assert usage["total_tokens"] == 5


def test_complete_json_raises_after_retries() -> None:
    client = _client(["nope", "still nope"], retries=2)
    with pytest.raises(ValueError):
        client.complete_json("system", "user")
