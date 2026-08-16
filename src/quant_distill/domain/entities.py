from __future__ import annotations

from typing import Any, Protocol

from quant_distill.domain.schemas import EntityMention, EntityOutput

ENTITY_SYSTEM = (
    "You extract every company or ticker referenced in a distilled "
    "summary. Return ONLY a JSON "
    "object: "
    '{"entities": [{"raw_mention": "as said", '
    '"entity_type": "<one of: ticker, company>", "company_name": "normalized name", '
    '"ticker": "RESOLVED_TICKER or null", "speaker": "who mentioned it or null", '
    '"direction": "<one of: long, short, neutral> or null", "confidence": 0.0..1.0, '
    '"context": "short quote or rationale"}]}. '
    "Each field must contain exactly one value, never a list of the options. "
    "Resolve company names to their US stock ticker where possible; if you cannot confidently "
    "resolve a ticker, set ticker to null."
)


class JsonCompletionClient(Protocol):
    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


def extract_entities(
    llm_client: JsonCompletionClient,
    distill_summary: str,
) -> tuple[EntityOutput, dict[str, Any]]:
    data, usage = llm_client.complete_json(
        ENTITY_SYSTEM,
        f"Distilled summary:\n{distill_summary}\n\nReturn the JSON object.",
    )
    return dedupe_entities(EntityOutput.model_validate(data)), usage or {}


def dedupe_entities(output: EntityOutput) -> EntityOutput:
    rows: list[EntityMention] = []
    seen: set[str] = set()
    for entity in output.entities:
        key = entity.ticker or entity.raw_mention
        norm = key.strip().upper()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        rows.append(entity)
    return EntityOutput(entities=rows)
