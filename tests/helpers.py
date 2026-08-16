from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx


class FakeLLM:
    def __init__(self, responses: list[tuple[dict[str, Any], dict[str, Any]]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]:
        self.calls.append((system, user))
        if self.responses:
            return self.responses.pop(0)
        lower = system.lower()
        if "market-sentiment classifier" in lower:
            return {
                "observations": [
                    {
                        "subject_type": "ticker",
                        "subject": "aapl",
                        "sentiment_label": "bullish",
                        "sentiment_score": 2.0,
                        "confidence": -1.0,
                        "reason": "positive guidance",
                    },
                    {
                        "subject_type": "market",
                        "subject": "ALL",
                        "sentiment_label": "neutral",
                    },
                ]
            }, {"total_tokens": 8}
        if "extract every company or ticker" in lower:
            return {
                "entities": [
                    {
                        "raw_mention": "Apple",
                        "entity_type": "company",
                        "company_name": "Apple Inc.",
                        "ticker": "aapl",
                        "direction": "long",
                        "confidence": 0.8,
                        "context": "positive iPhone commentary",
                    },
                    {
                        "raw_mention": "AAPL",
                        "entity_type": "ticker",
                        "ticker": "AAPL",
                    },
                ]
            }, {"total_tokens": 9}
        return {
            "summary": "**Topic 1**\n- Apple looked strong.",
            "key_topics": ["Apple"],
            "segments": [{"speaker": "Host", "role": "host", "summary": "Apple looked strong."}],
        }, {"total_tokens": 10}

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"


class FakeWatchlist:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict[str, Any]] = []

    def submit(self, **body: Any) -> str:
        if self.should_fail:
            raise httpx.ConnectError("failed")
        self.calls.append(body)
        return f"signal:{body['ticker']}"

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"


class FakeSentiment:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls: list[dict[str, Any]] = []

    def deliver(self, **body: Any) -> str:
        if self.should_fail:
            raise httpx.ConnectError("failed")
        self.calls.append(body)
        return f"sentiment:{body['subject']}"

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"


class FakeRunMetrics:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def record(self, **record: Any) -> None:
        self.records.append(record)

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"

    def list_runs(self, **query: Any) -> tuple[list[dict[str, Any]], int]:
        self.last_query = query
        rows = [
            {
                "id": index + 1,
                "request_id": record["request_id"],
                "endpoint": record["endpoint"],
                "source": record["source"],
                "source_item_id": record["source_item_id"],
                "model": record["model"],
                "started_at": record["started_at"],
                "completed_at": record["completed_at"],
                "duration_ms": record["duration_ms"],
                "input_chars": record["input_chars"],
                "output_chars": record["output_chars"],
                "token_usage": record["token_usage"],
                "status": record["status"],
            }
            for index, record in enumerate(self.records)
        ]
        if query.get("source"):
            rows = [row for row in rows if row["source"] == query["source"]]
        return rows[query.get("offset", 0) :][: query.get("limit", 50)], len(rows)

    def get_run(self, request_id: str) -> dict[str, Any] | None:
        rows, _ = self.list_runs()
        return next((row for row in rows if row["request_id"] == request_id), None)


class FakeJobs:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def enqueue(
        self,
        *,
        endpoint: str,
        request: dict[str, Any],
        source: str | None = None,
        source_item_id: str | None = None,
    ) -> dict[str, Any]:
        row = {
            "job_id": f"job-{len(self.rows) + 1}",
            "endpoint": endpoint,
            "status": "queued",
            "source": source,
            "source_item_id": source_item_id,
            "request": request,
            "result": None,
            "error": None,
            "attempts": 0,
            "created_at": datetime.now(timezone.utc),
            "started_at": None,
            "completed_at": None,
        }
        self.rows.append(row)
        return {"job_id": row["job_id"], "status": "queued", "created_at": row["created_at"]}

    def claim(self) -> dict[str, Any] | None:
        for row in self.rows:
            if row["status"] == "queued":
                row["status"] = "running"
                row["started_at"] = datetime.now(timezone.utc)
                row["attempts"] += 1
                return dict(row)
        return None

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        row = self._row(job_id)
        row.update(status="succeeded", result=result, error=None, completed_at=datetime.now(timezone.utc))

    def fail(self, job_id: str, error: str) -> None:
        row = self._row(job_id)
        row.update(status="failed", error=error[:512], completed_at=datetime.now(timezone.utc))

    def get(self, job_id: str) -> dict[str, Any] | None:
        return next((dict(row) for row in self.rows if row["job_id"] == job_id), None)

    def list_jobs(self, **query: Any) -> tuple[list[dict[str, Any]], int]:
        rows = [dict(row) for row in self.rows]
        if query.get("status"):
            rows = [row for row in rows if row["status"] == query["status"]]
        if query.get("source"):
            rows = [row for row in rows if row["source"] == query["source"]]
        return rows[query.get("offset", 0) :][: query.get("limit", 50)], len(rows)

    def counts_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in self.rows:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return counts

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"

    def _row(self, job_id: str) -> dict[str, Any]:
        return next(row for row in self.rows if row["job_id"] == job_id)
