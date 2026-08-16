from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _clamp(value: float | None, lo: float, hi: float) -> float | None:
    if value is None:
        return None
    return max(lo, min(hi, value))


class ErrorEnvelope(BaseModel):
    status: Literal["error"] = "error"
    code: str
    error: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str


class ReadinessDependency(BaseModel):
    name: str
    status: Literal["ok", "disabled", "unavailable"]
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ok", "error"]
    service: str
    dependencies: list[ReadinessDependency]


class CapabilitiesResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    model: str
    distill_prompt_version: str
    sentiment_prompt_version: str
    entity_prompt_version: str
    max_chunk_chars: int
    watchlist_enabled: bool
    sentiment_delivery_enabled: bool
    stateless: bool = True


class StatsResponse(BaseModel):
    status: Literal["ok"] = "ok"
    counters: dict[str, int]
    last_successful_llm_call_at: datetime | None = None
    last_watchlist_failure_at: datetime | None = None
    latency_ms: dict[str, dict[str, float | None]] = Field(default_factory=dict)


class RunQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str | None = None
    endpoint: str | None = None
    status: str | None = None
    source_item_id: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)
    order: Literal["asc", "desc"] = "desc"


class RunRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    request_id: str
    endpoint: str
    source: str | None = None
    source_item_id: str | None = None
    model: str
    distill_prompt_version: str | None = None
    sentiment_prompt_version: str | None = None
    entity_prompt_version: str | None = None
    started_at: datetime
    completed_at: datetime
    duration_ms: int
    input_chars: int
    output_chars: int
    token_usage: dict[str, Any] = Field(default_factory=dict)
    status: str
    error_type: str | None = None


class RunListResponse(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[RunRecord] = Field(default_factory=list)


class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    speaker: str | None = None
    role: str | None = None
    summary: str = ""


class DistillOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)


class SentimentObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_type: Literal["ticker", "sector", "theme", "market"] = "market"
    subject: str = "ALL"
    sentiment_label: Literal["bullish", "bearish", "neutral"] = "neutral"
    sentiment_score: float | None = None
    confidence: float | None = None
    horizon: str | None = None
    reason: str | None = None

    @field_validator("subject")
    @classmethod
    def _norm_subject(cls, value: str) -> str:
        return (value or "").strip() or "ALL"

    @field_validator("sentiment_score", mode="before")
    @classmethod
    def _clamp_score(cls, value: float | None) -> float | None:
        return _clamp(value, -1.0, 1.0)

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp_conf(cls, value: float | None) -> float | None:
        return _clamp(value, 0.0, 1.0)

    @model_validator(mode="after")
    def _normalize_ticker_subject(self) -> "SentimentObservation":
        if self.subject_type == "ticker":
            self.subject = self.subject.upper()
        return self


class SentimentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observations: list[SentimentObservation] = Field(default_factory=list)


class EntityMention(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_mention: str
    entity_type: Literal["ticker", "company"] = "company"
    company_name: str | None = None
    ticker: str | None = None
    speaker: str | None = None
    direction: Literal["long", "short", "neutral"] | None = None
    confidence: float | None = None
    context: str | None = None

    @field_validator("entity_type", mode="before")
    @classmethod
    def _coerce_entity_type(cls, value: object) -> object:
        if value in (None, ""):
            return "company"
        if value not in {"ticker", "company"}:
            return "company"
        return value

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, value: object) -> object:
        if value in (None, ""):
            return None
        if value not in {"long", "short", "neutral"}:
            return None
        return value

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, value: str | None) -> str | None:
        ticker = (value or "").strip().upper().lstrip("$")
        return ticker or None

    @field_validator("confidence", mode="before")
    @classmethod
    def _entity_clamp_conf(cls, value: float | None) -> float | None:
        return _clamp(value, 0.0, 1.0)


class EntityOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entities: list[EntityMention] = Field(default_factory=list)


class ProcessOptions(BaseModel):
    include_sentiment: bool = True
    include_entities: bool = True
    include_watchlist: bool = True
    watchlist_required: bool = False
    max_chunk_chars: int | None = Field(default=None, ge=1000, le=50000)


class DistillRequest(BaseModel):
    text: str = Field(..., min_length=1)
    source: str | None = None
    source_item_id: str | None = None
    options: ProcessOptions = Field(default_factory=lambda: ProcessOptions(
        include_sentiment=False,
        include_entities=False,
        include_watchlist=False,
    ))


class SummaryRequest(BaseModel):
    summary: str = Field(..., min_length=1)
    source: str | None = None
    source_item_id: str | None = None
    options: ProcessOptions = Field(default_factory=lambda: ProcessOptions(
        include_sentiment=False,
        include_entities=False,
        include_watchlist=False,
    ))


class ProcessRequest(BaseModel):
    source: str
    source_type: str
    source_item_id: str
    title: str | None = None
    text: str = Field(..., min_length=1)
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    options: ProcessOptions = Field(default_factory=ProcessOptions)


class SourceEnvelope(BaseModel):
    source: str
    source_type: str | None = None
    source_item_id: str
    observed_at: datetime | None = None


class ProcessingEnvelope(BaseModel):
    model: str
    distill_prompt_version: str | None = None
    sentiment_prompt_version: str | None = None
    entity_prompt_version: str | None = None
    chunk_count: int | None = None
    durations_ms: dict[str, int] = Field(default_factory=dict)
    token_usage: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DistillationEnvelope(BaseModel):
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)


class WatchlistEnrichment(BaseModel):
    entries: list[dict[str, Any]] = Field(default_factory=list)


class EnrichedEntity(BaseModel):
    raw_mention: str
    entity_type: str
    company_name: str | None = None
    ticker: str | None = None
    speaker: str | None = None
    direction: str | None = None
    confidence: float | None = None
    context: str | None = None
    watchlist: WatchlistEnrichment | None = None


class DistillEndpointResponse(BaseModel):
    status: Literal["ok"] = "ok"
    request_id: str
    processing: ProcessingEnvelope
    distillation: DistillationEnvelope


class SentimentEndpointResponse(BaseModel):
    status: Literal["ok"] = "ok"
    request_id: str
    processing: ProcessingEnvelope
    sentiment: SentimentOutput


class EntitiesEndpointResponse(BaseModel):
    status: Literal["ok"] = "ok"
    request_id: str
    processing: ProcessingEnvelope
    entities: dict[str, list[EnrichedEntity]]


class ProcessResponse(BaseModel):
    status: Literal["ok"] = "ok"
    request_id: str
    service: str
    source: SourceEnvelope
    processing: ProcessingEnvelope
    distillation: DistillationEnvelope
    sentiment: SentimentOutput | None = None
    entities: dict[str, list[EnrichedEntity]] | None = None
