from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import Any, Protocol

from quant_distill.domain.schemas import DistillOutput

log = logging.getLogger("quant_distill.distiller")

_DEPTH = (
    "Be EXHAUSTIVE. Cover EVERY distinct topic, company, ticker, guest, trade, and market "
    "discussed — do not omit any segment, and do not merge unrelated points into one line. "
    "Favor depth and breadth over brevity. Preserve concrete specifics wherever the source states "
    "them: tickers, company names, price levels, percentage moves, price targets, earnings and "
    "guidance numbers, analyst ratings, deals, macro data, and who made each call."
)
_SUMMARY_FORMAT = (
    "The summary value MUST be Markdown with bold numbered section headings and bullets. "
    "Return a self-contained detailed summary preserving ordering of topics. " + _DEPTH
)
_JSON_CONTRACT = (
    "Do NOT add any keys other than summary, key_topics, and segments. "
    "Return raw JSON only: no prose, no explanation, and no Markdown code fences."
)

DISTILL_SYSTEM = (
    "Summarize the following document into a thorough, self-contained, DETAILED summary. "
    + _SUMMARY_FORMAT
    + " "
    + _JSON_CONTRACT
)
REDUCE_SYSTEM = (
    "The following are DETAILED summaries of consecutive parts of ONE document. Merge them "
    "into a single summary that RETAINS ALL detail from every part — combine overlapping topics "
    "and drop only exact duplicates, but keep every distinct topic, company, ticker, number, "
    "rating, deal, trade, and named speaker that appears in ANY part. This is a merge, NOT a "
    "re-summarization: do not compress or shorten. The result must be at least as long and "
    "detailed as the parts combined. Order sections as the document progressed. "
    + _SUMMARY_FORMAT
    + " "
    + _JSON_CONTRACT
)
_HEADING = re.compile(r"^\s*(?:\d+\.\s+)?\*\*(.+?)\*\*\:?\s*$", re.MULTILINE)


class JsonCompletionClient(Protocol):
    def complete_json(self, system: str, user: str) -> tuple[dict[str, Any], dict[str, Any]]: ...


def _user_prompt(text: str) -> str:
    return f'Transcript:\n"""\n{text}\n"""\n\nReturn the JSON object.'


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, dict):
        for inner in value.values():
            yield from _iter_strings(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _iter_strings(inner)


def _dedupe_preserve(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _topics_from_summary(summary: str) -> list[str]:
    return _dedupe_preserve([match.group(1).strip() for match in _HEADING.finditer(summary or "")])


def _fallback_from_partials(partials: list[DistillOutput]) -> DistillOutput:
    merged_summary = "\n\n".join(
        f"### Chunk {idx}\n{(partial.summary or '').strip()}" for idx, partial in enumerate(partials, 1)
    ).strip()
    topics = _dedupe_preserve([topic for partial in partials for topic in partial.key_topics])
    if not topics:
        topics = _topics_from_summary(merged_summary)
    segments = [segment for partial in partials for segment in partial.segments][:200]
    return DistillOutput(summary=merged_summary, key_topics=topics, segments=segments)


def _is_thin_reduce_output(
    *, reduced: DistillOutput, partials: list[DistillOutput], total_partial_chars: int
) -> bool:
    partial_topic_count = sum(1 for partial in partials if partial.key_topics)
    partial_segment_count = sum(1 for partial in partials if partial.segments)
    reduced_chars = len((reduced.summary or "").strip())
    if reduced_chars < max(400, int(total_partial_chars * 0.15)):
        return True
    if (not reduced.key_topics and partial_topic_count > 0) or (
        not reduced.segments and partial_segment_count > 0
    ):
        return True
    return False


def _coerce_distill(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("summary"), str) and data["summary"].strip():
        return data
    if isinstance(data, str):
        return {"summary": data}
    if not isinstance(data, dict):
        return {"summary": str(data)}

    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            coerced = _coerce_distill(inner)
            if coerced.get("summary"):
                return coerced
        if isinstance(inner, str) and inner.strip():
            return {"summary": inner}

    for alt in ("markdown", "document", "content", "text", "body", "summary_markdown"):
        if isinstance(data.get(alt), str) and data[alt].strip():
            return {**data, "summary": data[alt]}

    if data.get("summary") is not None:
        joined = "\n\n".join(_iter_strings(data["summary"]))
        if joined.strip():
            return {**data, "summary": joined}

    candidates = list(_iter_strings(data))
    if candidates:
        return {**data, "summary": max(candidates, key=len)}
    return data


def _merge_usage(acc: dict[str, Any], usage: dict[str, Any]) -> None:
    for key, value in (usage or {}).items():
        if isinstance(value, (int, float)):
            acc[key] = acc.get(key, 0) + value
        else:
            acc[key] = value


def distill(
    llm_client: JsonCompletionClient,
    text: str,
    *,
    max_chunk_chars: int = 6000,
) -> tuple[DistillOutput, dict[str, Any], int]:
    if len(text) <= max_chunk_chars:
        data, usage = llm_client.complete_json(DISTILL_SYSTEM, _user_prompt(text))
        return DistillOutput.model_validate(_coerce_distill(data)), usage or {}, 1

    chunks = _chunks(text, max_chunk_chars)
    partials: list[DistillOutput] = []
    total_usage: dict[str, Any] = {}
    for chunk in chunks:
        data, usage = llm_client.complete_json(DISTILL_SYSTEM, _user_prompt(chunk))
        partials.append(DistillOutput.model_validate(_coerce_distill(data)))
        _merge_usage(total_usage, usage or {})

    combined = "\n\n".join(
        f"### Chunk {idx}\n{(partial.summary or '').strip()}" for idx, partial in enumerate(partials, 1)
    )
    data, usage = llm_client.complete_json(REDUCE_SYSTEM, _user_prompt(combined))
    _merge_usage(total_usage, usage or {})
    reduced = DistillOutput.model_validate(_coerce_distill(data))
    total_partial_chars = sum(len((partial.summary or "").strip()) for partial in partials)
    if _is_thin_reduce_output(
        reduced=reduced,
        partials=partials,
        total_partial_chars=total_partial_chars,
    ):
        reduced = _fallback_from_partials(partials)
    return reduced, total_usage, len(chunks)
