from __future__ import annotations

from typing import Any

from webtest import TestApp

from quant_distill.api.app import create_app
from quant_distill.domain.service import QuantDistillService
from quant_distill.domain.stats import StatsCollector
from quant_distill.workers.job_worker import JobWorker
from tests.helpers import FakeJobs, FakeLLM, FakeRunMetrics, FakeSentiment, FakeWatchlist


def _service(*, watchlist_fail: bool = False, sentiment_fail: bool = False) -> QuantDistillService:
    settings_obj = type(
        "TestSettings",
        (),
        {
            "llm_model": "llama3.1",
            "distill_prompt_version": "v1",
            "sentiment_prompt_version": "v1",
            "entity_prompt_version": "v1",
            "distill_max_chunk_chars": 100,
            "sentiment_required": False,
            "max_page_size": 100,
        },
    )()
    return QuantDistillService(
        llm_client=FakeLLM(),
        watchlist_client=FakeWatchlist(should_fail=watchlist_fail),
        sentiment_client=FakeSentiment(should_fail=sentiment_fail),
        jobs_repository=FakeJobs(),
        stats=StatsCollector(),
        settings_obj=settings_obj,
    )


def _drain(service: QuantDistillService) -> None:
    worker = JobWorker(jobs_repository=service.jobs, service=service)
    while worker.run_once():
        pass


def _submit(client: TestApp, body: dict[str, Any]) -> str:
    accepted = client.post_json("/v1/process", body, status=202).json
    assert accepted["status"] == "accepted"
    assert accepted["job_status"] == "queued"
    return str(accepted["job_id"])


def test_process_happy_path() -> None:
    service = _service()
    client = TestApp(create_app(service=service))
    job_id = _submit(
        client,
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
    assert client.get(f"/v1/jobs/{job_id}").json["status"] == "queued"

    _drain(service)

    job = client.get(f"/v1/jobs/{job_id}").json
    assert job["status"] == "succeeded"
    result = job["result"]
    assert result["status"] == "ok"
    assert result["distillation"]["summary"].startswith("**Topic 1**")
    assert result["sentiment"]["observations"][0]["subject"] == "AAPL"
    assert result["entities"]["items"][0]["ticker"] == "AAPL"
    assert result["entities"]["items"][0]["watchlist"]["entries"][0]["signal_id"] == "signal:AAPL"
    assert service.sentiment_client.calls[0]["subject"] == "AAPL"
    assert service.watchlist.calls[0]["ticker"] == "AAPL"


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


def test_process_required_enrichment_marks_job_failed() -> None:
    service = _service(watchlist_fail=True)
    client = TestApp(create_app(service=service))
    job_id = _submit(
        client,
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
    )
    _drain(service)

    job = client.get(f"/v1/jobs/{job_id}").json
    assert job["status"] == "failed"
    assert "watchlist enrichment failed" in job["error"]


def test_process_without_job_store_returns_503() -> None:
    service = _service()
    service.jobs = None
    client = TestApp(create_app(service=service))
    response = client.post_json(
        "/v1/process",
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc",
            "text": "Apple looked strong.",
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


def test_queue_endpoint_reports_in_flight() -> None:
    service = _service()
    client = TestApp(create_app(service=service))
    payload = client.get("/queue").json
    assert payload["status"] == "ok"
    # The /queue request itself is the only thing in flight while it is served.
    assert payload["in_flight_by_endpoint"] == {"/queue": 1}
    assert payload["in_flight"][0]["method"] == "GET"
    assert service.stats.in_flight() == []


def test_process_records_run_metrics() -> None:
    metrics = FakeRunMetrics()
    service = _service()
    service.run_metrics = metrics
    client = TestApp(create_app(service=service))

    _submit(
        client,
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc123",
            "text": "Apple looked strong.",
            "metadata": {},
        },
    )
    _drain(service)

    assert len(metrics.records) == 1
    record = metrics.records[0]
    assert record["endpoint"] == "/v1/process"
    assert record["input_chars"] == len("Apple looked strong.")
    assert record["output_chars"] > 0
    assert record["token_usage"]["total_tokens"] == 27


def test_runs_listing_and_detail() -> None:
    metrics = FakeRunMetrics()
    service = _service()
    service.run_metrics = metrics
    client = TestApp(create_app(service=service))
    _submit(
        client,
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc123",
            "text": "Apple looked strong.",
            "metadata": {},
        },
    )
    _drain(service)

    listing = client.get("/v1/runs?source=quant_youtube&limit=10").json
    assert listing["total"] == 1
    assert listing["items"][0]["source"] == "quant_youtube"
    assert listing["items"][0]["endpoint"] == "/v1/process"
    request_id = listing["items"][0]["request_id"]

    detail = client.get(f"/v1/runs/{request_id}").json
    assert detail["request_id"] == request_id
    assert client.get("/v1/runs?source=other").json["total"] == 0
    assert client.get("/v1/runs/missing", status=404).json["code"] == "not_found"
    assert client.get("/v1/runs?limit=0", status=422).json["code"] == "validation_error"


def test_runs_without_store_returns_503() -> None:
    service = _service()
    service.run_metrics = None
    client = TestApp(create_app(service=service))
    assert client.get("/v1/runs", status=503).json["code"] == "dependency_unavailable"


def test_large_payload_is_accepted() -> None:
    service = _service()
    client = TestApp(create_app(service=service))
    job_id = _submit(
        client,
        {
            "source": "quant_cnbc",
            "source_type": "broadcast",
            "source_item_id": "big",
            "text": "Apple looked strong. " * 10000,
            "metadata": {},
            "options": {"include_sentiment": False, "include_entities": False},
        },
    )
    _drain(service)
    assert client.get(f"/v1/jobs/{job_id}").json["status"] == "succeeded"


def test_jobs_listing_filters_by_status() -> None:
    service = _service()
    client = TestApp(create_app(service=service))
    _submit(
        client,
        {
            "source": "quant_cnbc",
            "source_type": "broadcast",
            "source_item_id": "abc",
            "text": "Apple looked strong.",
            "options": {"include_sentiment": False, "include_entities": False},
        },
    )
    assert client.get("/v1/jobs?status=queued").json["total"] == 1
    assert client.get("/queue").json["jobs"] == {"queued": 1}

    _drain(service)

    assert client.get("/v1/jobs?status=succeeded").json["total"] == 1
    assert client.get("/v1/jobs?status=queued").json["total"] == 0
    assert client.get("/v1/jobs/missing", status=404).json["code"] == "not_found"


def test_failed_run_is_recorded() -> None:
    metrics = FakeRunMetrics()
    service = _service(watchlist_fail=True)
    service.run_metrics = metrics
    client = TestApp(create_app(service=service))
    _submit(
        client,
        {
            "source": "quant_youtube",
            "source_type": "youtube",
            "source_item_id": "abc123",
            "text": "Apple looked strong.",
            "metadata": {},
            "options": {"include_entities": True, "include_watchlist": True, "watchlist_required": True},
        },
    )
    _drain(service)

    assert len(metrics.records) == 1
    record = metrics.records[0]
    assert record["status"] == "failed"
    assert record["error_type"].startswith("DependencyUnavailableError")
    assert service.stats.counters["failure:/v1/process"] == 1
    assert client.get("/v1/runs?status=failed").json["items"][0]["status"] == "failed"
