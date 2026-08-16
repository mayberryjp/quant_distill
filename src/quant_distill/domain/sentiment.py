from __future__ import annotations

from typing import Any, Protocol

from quant_distill.domain.schemas import SentimentOutput

SENTIMENT_SYSTEM = (
    "You are a market-sentiment classifier. Given a distilled summary, "
    "return ONLY a JSON object: "
    '{"observations": [{"subject_type": "<one of: ticker, sector, theme, market>", '
    '"subject": "AAPL or sector/theme name or ALL", '
    '"sentiment_label": "<one of: bullish, bearish, neutral>", '
    '"sentiment_score": -1.0..1.0, "confidence": 0.0..1.0, '
    '"horizon": "<one of: intraday, 1d, 5d, 30d>", "reason": "short rationale"}]}. '
    "Each field must contain exactly one value, never a list of the options. "
    "Include one observation per ticker/sector/theme discussed, plus one "
    'subject_type "market" with subject "ALL" for the overall tone.'
)


class JsonCompletionClient(Protocol):
    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


def extract_sentiment(
    llm_client: JsonCompletionClient,
    distill_summary: str,
) -> tuple[SentimentOutput, dict[str, Any]]:
    data, usage = llm_client.complete_json(
        SENTIMENT_SYSTEM,
        f"Distilled summary:\n{distill_summary}\n\nReturn the JSON object.",
    )
    return SentimentOutput.model_validate(data), usage or {}
