from __future__ import annotations

import pytest

from quant_distill.domain.service import QuantDistillService
from quant_distill.domain.stats import StatsCollector
from tests.helpers import FakeLLM, FakeWatchlist


@pytest.fixture
def service() -> QuantDistillService:
    settings_obj = type(
        "TestSettings",
        (),
        {
            "llm_model": "llama3.1",
            "distill_prompt_version": "v1",
            "sentiment_prompt_version": "v1",
            "entity_prompt_version": "v1",
            "distill_max_chunk_chars": 12,
        },
    )()
    return QuantDistillService(
        llm_client=FakeLLM(),
        watchlist_client=FakeWatchlist(),
        stats=StatsCollector(),
        settings_obj=settings_obj,
    )
