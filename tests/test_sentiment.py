from __future__ import annotations

from quant_distill.domain.sentiment import extract_sentiment


class FakeLLM:
    def complete_json(self, _system: str, _user: str):
        return {
            "observations": [
                {
                    "subject_type": "ticker",
                    "subject": " AAPL ",
                    "sentiment_label": "bullish",
                    "sentiment_score": 2.0,
                    "confidence": -1.0,
                }
            ]
        }, {"total_tokens": 12}


def test_extract_sentiment_clamps_values() -> None:
    out, usage = extract_sentiment(FakeLLM(), "summary")
    obs = out.observations[0]
    assert obs.subject == "AAPL"
    assert obs.sentiment_score == 1.0
    assert obs.confidence == 0.0
    assert usage["total_tokens"] == 12
