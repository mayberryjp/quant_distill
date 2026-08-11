from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * p)))
    return round(ordered[idx], 2)


class StatsCollector:
    def __init__(self) -> None:
        self.counters: dict[str, int] = defaultdict(int)
        self.latency_samples: dict[str, list[float]] = defaultdict(list)
        self.last_successful_llm_call_at: datetime | None = None
        self.last_watchlist_failure_at: datetime | None = None
        self.last_momentum_failure_at: datetime | None = None

    def increment(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def record_latency(self, endpoint: str, latency_ms: float) -> None:
        samples = self.latency_samples[endpoint]
        samples.append(latency_ms)
        if len(samples) > 200:
            del samples[0]

    def mark_llm_success(self) -> None:
        self.last_successful_llm_call_at = datetime.now(timezone.utc)

    def mark_watchlist_failure(self) -> None:
        self.last_watchlist_failure_at = datetime.now(timezone.utc)

    def mark_momentum_failure(self) -> None:
        self.last_momentum_failure_at = datetime.now(timezone.utc)

    def snapshot(self) -> dict[str, Any]:
        latency = {
            endpoint: {
                "p50": _percentile(samples, 0.5),
                "p95": _percentile(samples, 0.95),
            }
            for endpoint, samples in self.latency_samples.items()
        }
        return {
            "status": "ok",
            "counters": dict(self.counters),
            "last_successful_llm_call_at": self.last_successful_llm_call_at,
            "last_watchlist_failure_at": self.last_watchlist_failure_at,
            "last_momentum_failure_at": self.last_momentum_failure_at,
            "latency_ms": latency,
        }
