from __future__ import annotations

from collections.abc import Callable
from datetime import timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from quant_distill.config import settings
from quant_distill.domain import distiller, entities, sentiment
from quant_distill.domain.schemas import (
    DistillEndpointResponse,
    DistillationEnvelope,
    EntityMention,
    EntitiesEndpointResponse,
    EnrichedEntity,
    ProcessRequest,
    ProcessOptions,
    ProcessResponse,
    ProcessingEnvelope,
    SentimentEndpointResponse,
    SourceEnvelope,
    SummaryRequest,
    WatchlistEnrichment,
)
from quant_distill.domain.stats import StatsCollector
from quant_distill.repository.llm_client import OpenAICompatLLMClient
from quant_distill.repository.watchlist_client import WatchlistClient

SERVICE_NAME = "quant-distill-api"


class DependencyUnavailableError(RuntimeError):
    def __init__(self, code: str, error: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.error = error
        self.detail = detail


def _ms(start: float) -> int:
    return round((perf_counter() - start) * 1000)


def _merge_usage(total: dict[str, int | float], usage: dict[str, Any]) -> None:
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            total[key] = total.get(key, 0) + value


class QuantDistillService:
    def __init__(
        self,
        *,
        llm_client: Any,
        watchlist_client: Any | None = None,
        stats: StatsCollector | None = None,
        settings_obj: Any = settings,
        now: Callable[[], object] | None = None,
    ) -> None:
        self.llm = llm_client
        self.watchlist = watchlist_client
        self.stats = stats or StatsCollector()
        self.settings = settings_obj
        self.now = now

    def capabilities(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "model": self.settings.llm_model,
            "distill_prompt_version": self.settings.distill_prompt_version,
            "sentiment_prompt_version": self.settings.sentiment_prompt_version,
            "entity_prompt_version": self.settings.entity_prompt_version,
            "max_chunk_chars": self.settings.distill_max_chunk_chars,
            "watchlist_enabled": bool(self.watchlist and self.settings.watchlist_enabled),
            "stateless": True,
        }

    def readiness(self) -> dict[str, Any]:
        ok, detail = self.llm.readiness()
        dependencies = [{"name": "llm", "status": "ok" if ok else "unavailable", "detail": detail}]

        if self.settings.watchlist_enabled and self.watchlist is not None:
            w_ok, w_detail = self.watchlist.readiness()
            dependencies.append(
                {"name": "watchlist", "status": "ok" if w_ok else "unavailable", "detail": w_detail}
            )
        else:
            dependencies.append({"name": "watchlist", "status": "disabled", "detail": None})

        overall_ok = all(dep["status"] != "unavailable" for dep in dependencies if dep["name"] == "llm")
        return {"ok": overall_ok, "dependencies": dependencies}

    def stats_snapshot(self) -> dict[str, Any]:
        return self.stats.snapshot()

    def distill(self, request: Any) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/distill"
        start = perf_counter()
        out, usage, chunk_count = distiller.distill(
            self.llm,
            request.text,
            max_chunk_chars=request.options.max_chunk_chars or self.settings.distill_max_chunk_chars,
        )
        self.stats.mark_llm_success()
        elapsed = _ms(start)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, elapsed)
        return DistillEndpointResponse(
            request_id=request_id,
            processing=ProcessingEnvelope(
                model=self.settings.llm_model,
                distill_prompt_version=self.settings.distill_prompt_version,
                chunk_count=chunk_count,
                token_usage=usage,
                durations_ms={"distill": elapsed, "total": elapsed},
            ),
            distillation=DistillationEnvelope(**out.model_dump()),
        ).model_dump(mode="json")

    def sentiment(self, request: SummaryRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/sentiment"
        start = perf_counter()
        out, usage = sentiment.extract_sentiment(self.llm, request.summary)
        self.stats.mark_llm_success()
        elapsed = _ms(start)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, elapsed)
        return SentimentEndpointResponse(
            request_id=request_id,
            processing=ProcessingEnvelope(
                model=self.settings.llm_model,
                sentiment_prompt_version=self.settings.sentiment_prompt_version,
                token_usage=usage,
                durations_ms={"sentiment": elapsed, "total": elapsed},
            ),
            sentiment=out,
        ).model_dump(mode="json")

    def entities(self, request: SummaryRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/entities"
        start = perf_counter()
        out, usage = entities.extract_entities(self.llm, request.summary)
        self.stats.mark_llm_success()
        items, warnings = self._enrich_entities(out.entities, request.options)
        elapsed = _ms(start)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, elapsed)
        return EntitiesEndpointResponse(
            request_id=request_id,
            processing=ProcessingEnvelope(
                model=self.settings.llm_model,
                entity_prompt_version=self.settings.entity_prompt_version,
                token_usage=usage,
                warnings=warnings,
                durations_ms={"entities": elapsed, "total": elapsed},
            ),
            entities={"items": items},
        ).model_dump(mode="json")

    def process(self, request: ProcessRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/process"
        started = perf_counter()
        total_usage: dict[str, int | float] = {}
        durations: dict[str, int] = {}
        warnings: list[str] = []

        distill_start = perf_counter()
        distill_out, distill_usage, chunk_count = distiller.distill(
            self.llm,
            request.text,
            max_chunk_chars=request.options.max_chunk_chars or self.settings.distill_max_chunk_chars,
        )
        self.stats.mark_llm_success()
        durations["distill"] = _ms(distill_start)
        _merge_usage(total_usage, distill_usage)

        sentiment_out = None
        if request.options.include_sentiment:
            sent_start = perf_counter()
            sentiment_out, sent_usage = sentiment.extract_sentiment(self.llm, distill_out.summary)
            self.stats.mark_llm_success()
            durations["sentiment"] = _ms(sent_start)
            _merge_usage(total_usage, sent_usage)

        entity_items = None
        if request.options.include_entities:
            ent_start = perf_counter()
            entity_out, ent_usage = entities.extract_entities(self.llm, distill_out.summary)
            self.stats.mark_llm_success()
            items, entity_warnings = self._enrich_entities(entity_out.entities, request.options)
            warnings.extend(entity_warnings)
            durations["entities"] = _ms(ent_start)
            _merge_usage(total_usage, ent_usage)
            entity_items = {"items": items}

        durations["total"] = _ms(started)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, durations["total"])

        return ProcessResponse(
            request_id=request_id,
            service=SERVICE_NAME,
            source=SourceEnvelope(
                source=request.source,
                source_type=request.source_type,
                source_item_id=request.source_item_id,
                observed_at=(request.observed_at.astimezone(timezone.utc) if request.observed_at else None),
            ),
            processing=ProcessingEnvelope(
                model=self.settings.llm_model,
                distill_prompt_version=self.settings.distill_prompt_version,
                sentiment_prompt_version=(
                    self.settings.sentiment_prompt_version if request.options.include_sentiment else None
                ),
                entity_prompt_version=(
                    self.settings.entity_prompt_version if request.options.include_entities else None
                ),
                chunk_count=chunk_count,
                durations_ms=durations,
                token_usage=total_usage,
                warnings=warnings,
            ),
            distillation=DistillationEnvelope(**distill_out.model_dump()),
            sentiment=sentiment_out,
            entities=entity_items,
        ).model_dump(mode="json")

    def _enrich_entities(
        self,
        entity_rows: list[EntityMention],
        options: ProcessOptions,
    ) -> tuple[list[EnrichedEntity], list[str]]:
        warnings: list[str] = []
        enriched: list[EnrichedEntity] = []
        for row in entity_rows:
            watchlist_data = None
            if row.ticker and options.include_watchlist and self.watchlist is not None:
                try:
                    watchlist_data = WatchlistEnrichment(entries=self.watchlist.get_entries(row.ticker))
                except Exception as exc:
                    self.stats.mark_watchlist_failure()
                    if options.watchlist_required:
                        raise DependencyUnavailableError(
                            "dependency_unavailable",
                            "required dependency unavailable",
                            f"watchlist enrichment failed: {type(exc).__name__}",
                        ) from exc
                    warnings.append(f"watchlist enrichment failed for {row.ticker}: {type(exc).__name__}")
            enriched.append(
                EnrichedEntity(
                    **row.model_dump(),
                    watchlist=watchlist_data,
                )
            )
        return enriched, warnings


def build_default_service() -> QuantDistillService:
    llm = OpenAICompatLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
        json_mode=settings.llm_json_mode,
        num_ctx=settings.llm_num_ctx,
    )
    watchlist = None
    if settings.watchlist_enabled and settings.watchlist_api_url:
        watchlist = WatchlistClient(
            base_url=settings.watchlist_api_url,
            api_key=settings.watchlist_api_key,
            timeout=settings.watchlist_timeout,
        )
    return QuantDistillService(llm_client=llm, watchlist_client=watchlist)
