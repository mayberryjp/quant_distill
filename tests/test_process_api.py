from __future__ import annotations

from webtest import TestApp

from quant_distill.api.app import create_app
from quant_distill.domain.service import QuantDistillService
from quant_distill.domain.stats import StatsCollector
from tests.helpers import FakeLLM, FakeWatchlist


def _service(*, watchlist_fail: bool = False) -> QuantDistillService:
    settings_obj = type(
        "TestSettings",
        (),
        {
            "llm_model": "llama3.1",
            "distill_prompt_version": "v1",
            "sentiment_prompt_version": "v1",
            "entity_prompt_version": "v1",
            "distill_max_chunk_chars": 100,
            "watchlist_enabled": True,
        },
    )()
    return QuantDistillService(
        llm_client=FakeLLM(),
        watchlist_client=FakeWatchlist(should_fail=watchlist_fail),
        stats=StatsCollector(),
        settings_obj=settings_obj,
    )


def test_process_happy_path() -> None:
    client = TestApp(create_app(service=_service()))
    response = client.post_json(
        "/v1/process",
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc123",
            "text": "Apple looked strong.",
            "metadata": {},
            "options": {
                "include_sentiment": True,
                "include_entities": True,
                "include_watchlist": True,
            },
        },
    )
    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["distillation"]["summary"].startswith("**Topic 1**")
    assert response.json["sentiment"]["observations"][0]["subject"] == "AAPL"
    assert response.json["entities"]["items"][0]["ticker"] == "AAPL"
    assert response.json["entities"]["items"][0]["watchlist"]["entries"][0]["submitted_ticker"] == "AAPL"


def test_distill_validation_error() -> None:
    client = TestApp(create_app(service=_service()))
    response = client.post_json("/v1/distill", {"text": ""}, status=422)
    assert response.json["code"] == "validation_error"


def test_entities_optional_enrichment_degrades() -> None:
    client = TestApp(create_app(service=_service(watchlist_fail=True)))
    response = client.post_json(
        "/v1/entities",
        {
            "summary": "Apple looked strong.",
            "options": {"include_watchlist": True},
        },
    )
    assert response.status_code == 200
    assert len(response.json["processing"]["warnings"]) == 1


def test_process_required_enrichment_503() -> None:
    client = TestApp(create_app(service=_service(watchlist_fail=True)))
    response = client.post_json(
        "/v1/process",
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc123",
            "text": "Apple looked strong.",
            "metadata": {},
            "options": {
                "include_sentiment": True,
                "include_entities": True,
                "include_watchlist": True,
                "watchlist_required": True,
            },
        },
        status=503,
    )
    assert response.json["code"] == "dependency_unavailable"


def test_capabilities_and_stats() -> None:
    service = _service()
    client = TestApp(create_app(service=service))
    assert client.get("/capabilities").json["service"] == "quant-distill-api"
    stats = client.get("/stats").json
    assert stats["status"] == "ok"
