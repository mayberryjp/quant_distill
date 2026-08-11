from __future__ import annotations

from quant_distill.domain.entities import dedupe_entities, extract_entities
from quant_distill.domain.schemas import EntityOutput


class FakeLLM:
    def complete_json(self, _system: str, _user: str):
        return {
            "entities": [
                {"raw_mention": "Apple", "entity_type": "index", "ticker": "aapl", "direction": "up"},
                {"raw_mention": "AAPL", "entity_type": "ticker", "ticker": "AAPL"},
            ]
        }, {"total_tokens": 9}


def test_extract_entities_coerces_and_dedupes() -> None:
    out, usage = extract_entities(FakeLLM(), "summary")
    assert len(out.entities) == 1
    assert out.entities[0].entity_type == "company"
    assert out.entities[0].direction is None
    assert out.entities[0].ticker == "AAPL"
    assert usage["total_tokens"] == 9


def test_dedupe_entities_prefers_first_key() -> None:
    output = EntityOutput.model_validate(
        {
            "entities": [
                {"raw_mention": "Apple", "ticker": "AAPL"},
                {"raw_mention": "AAPL", "ticker": "AAPL"},
            ]
        }
    )
    deduped = dedupe_entities(output)
    assert len(deduped.entities) == 1
