from __future__ import annotations

import pytest

from quant_distill.domain.schemas import EntityMention, ProcessOptions
from quant_distill.domain.service import DependencyUnavailableError
from tests.test_process_api import _service


def test_optional_enrichment_warnings() -> None:
    service = _service(watchlist_fail=True)
    items, warnings = service._enrich_entities(
        [EntityMention(raw_mention="Apple", ticker="AAPL")],
        ProcessOptions(include_watchlist=True),
    )
    assert len(items) == 1
    assert len(warnings) == 1


def test_required_watchlist_enrichment_raises() -> None:
    service = _service(watchlist_fail=True)
    with pytest.raises(DependencyUnavailableError):
        service._enrich_entities(
            [EntityMention(raw_mention="Apple", ticker="AAPL")],
            ProcessOptions(include_watchlist=True, watchlist_required=True),
        )
