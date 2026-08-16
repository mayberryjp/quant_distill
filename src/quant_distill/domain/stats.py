from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone
import threading
from time import perf_counter
from typing import Any
from uuid import uuid4

# Set by the server entrypoint; the WSGI server object is only reachable from there.
_server_info_provider: Callable[[], dict[str, Any]] | None = None


def set_server_info_provider(provider: Callable[[], dict[str, Any]] | None) -> None:
    global _server_info_provider
    _server_info_provider = provider


def server_info() -> dict[str, Any]:
    if _server_info_provider is None:
        return {"available": False}
    try:
        return {"available": True, **_server_info_provider()}
    except Exception:
        return {"available": False}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


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
        self._lock = threading.Lock()
        self._in_flight: dict[str, dict[str, Any]] = {}

    def request_started(self, endpoint: str, method: str = "") -> str:
        token = uuid4().hex
        with self._lock:
            self._in_flight[token] = {
                "endpoint": endpoint,
                "method": method,
                "started_at": datetime.now(timezone.utc),
                "started": perf_counter(),
                "thread": threading.current_thread().name,
            }
        return token

    def request_finished(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._in_flight.pop(token, None)

    def in_flight(self) -> list[dict[str, Any]]:
        now = perf_counter()
        with self._lock:
            entries = list(self._in_flight.items())
        active = [
            {
                "request_token": token,
                "endpoint": entry["endpoint"],
                "method": entry["method"],
                "thread": entry["thread"],
                "started_at": _iso(entry["started_at"]),
                "age_ms": round((now - entry["started"]) * 1000),
            }
            for token, entry in entries
        ]
        active.sort(key=lambda item: item["age_ms"], reverse=True)
        return active

    def in_flight_by_endpoint(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        with self._lock:
            for entry in self._in_flight.values():
                counts[entry["endpoint"]] += 1
        return dict(counts)

    def queue_snapshot(self) -> dict[str, Any]:
        active = self.in_flight()
        return {
            "status": "ok",
            "observed_at": _iso(datetime.now(timezone.utc)),
            "server": server_info(),
            "in_flight_total": len(active),
            "in_flight_by_endpoint": self.in_flight_by_endpoint(),
            "in_flight": active,
        }

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

    def snapshot(self) -> dict[str, Any]:
        latency = {
            endpoint: {
                "p50": _percentile(samples, 0.5),
                "p95": _percentile(samples, 0.95),
            }
            for endpoint, samples in self.latency_samples.items()
        }
        in_flight = self.in_flight_by_endpoint()
        return {
            "status": "ok",
            "counters": dict(self.counters),
            "last_successful_llm_call_at": _iso(self.last_successful_llm_call_at),
            "last_watchlist_failure_at": _iso(self.last_watchlist_failure_at),
            "latency_ms": latency,
            "queue": {
                "in_flight_total": sum(in_flight.values()),
                "in_flight": in_flight,
                "server": server_info(),
            },
        }
