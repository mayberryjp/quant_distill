from __future__ import annotations

from quant_distill.domain.distiller import distill


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def complete_json(self, _system: str, _user: str):
        self.calls += 1
        return self.responses.pop(0)


def test_single_pass() -> None:
    llm = FakeLLM([
        ({"summary": "buy AAPL", "key_topics": ["apple"], "segments": []}, {"total_tokens": 10})
    ])
    out, usage, chunk_count = distill(llm, "short text", max_chunk_chars=50)
    assert out.summary == "buy AAPL"
    assert usage["total_tokens"] == 10
    assert llm.calls == 1
    assert chunk_count == 1


def test_map_reduce_falls_back_when_reduce_too_thin() -> None:
    llm = FakeLLM(
        [
            ({"summary": "part1", "key_topics": ["AI"], "segments": [{"summary": "s1"}]}, {"total_tokens": 10}),
            ({"summary": "part2", "key_topics": ["Semis"], "segments": [{"summary": "s2"}]}, {"total_tokens": 10}),
            ({"summary": "thin", "key_topics": [], "segments": []}, {"total_tokens": 10}),
        ]
    )
    out, usage, chunk_count = distill(llm, "x" * 25, max_chunk_chars=13)
    assert "Chunk 1" in out.summary
    assert "Chunk 2" in out.summary
    assert out.key_topics == ["AI", "Semis"]
    assert len(out.segments) == 2
    assert usage["total_tokens"] == 30
    assert chunk_count == 2
