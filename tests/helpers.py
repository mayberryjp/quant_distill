from __future__ import annotations

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

    def get_entries(self, ticker: str) -> list[dict[str, Any]]:
        if self.should_fail:
            raise httpx.ConnectError("failed")
        return [{"watchlist_entry_id": f"watchlist:test:mention:{ticker.upper()}", "submitted_ticker": ticker.upper()}]

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"


class FakeMomentum:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def get_latest(self, ticker: str) -> dict[str, Any] | None:
        if self.should_fail:
            raise httpx.ConnectError("failed")
        return {
            "ticker": ticker.upper(),
            "bar_date": "2026-08-11",
            "close": 210.0,
            "momentum_5d": 0.12,
            "momentum_15d": 0.21,
            "momentum_30d": 0.35,
            "is_momentum": True,
            "bars_available": 31,
        }

    def readiness(self) -> tuple[bool, str]:
        return True, "ok"
