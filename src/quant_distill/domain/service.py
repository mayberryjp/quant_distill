from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx

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
from quant_distill.repository.run_metrics import RunMetricsRepository
from quant_distill.repository.sentiment_client import SentimentClient
from quant_distill.repository.watchlist_client import WatchlistClient

SERVICE_NAME = "quant-distill-api"
log = logging.getLogger("quant_distill.service")


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


def _output_chars(payload: dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":")))


@contextmanager
def _llm_guard(stage: str) -> Iterator[None]:
    try:
        yield
    except httpx.HTTPError as exc:
        raise DependencyUnavailableError(
            "dependency_unavailable",
            "required dependency unavailable",
            f"llm {stage} call failed: {type(exc).__name__}",
        ) from exc


class QuantDistillService:
    def __init__(
        self,
        *,
        llm_client: Any,
        watchlist_client: Any | None = None,
        sentiment_client: Any | None = None,
        run_metrics_repository: Any | None = None,
        stats: StatsCollector | None = None,
        settings_obj: Any = settings,
        now: Callable[[], object] | None = None,
    ) -> None:
        self.llm = llm_client
        self.watchlist = watchlist_client
        self.sentiment_client = sentiment_client
        self.run_metrics = run_metrics_repository
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
            "watchlist_enabled": bool(self.watchlist),
            "sentiment_delivery_enabled": bool(self.sentiment_client),
            "stateless": True,
        }

    def readiness(self) -> dict[str, Any]:
        ok, detail = self.llm.readiness()
        dependencies = [{"name": "llm", "status": "ok" if ok else "unavailable", "detail": detail}]

        if self.watchlist is not None:
            w_ok, w_detail = self.watchlist.readiness()
            dependencies.append(
                {"name": "watchlist", "status": "ok" if w_ok else "unavailable", "detail": w_detail}
            )
        else:
            dependencies.append({"name": "watchlist", "status": "disabled", "detail": None})

        if self.sentiment_client is not None:
            s_ok, s_detail = self.sentiment_client.readiness()
            dependencies.append(
                {"name": "sentiment", "status": "ok" if s_ok else "unavailable", "detail": s_detail}
            )
        else:
            dependencies.append({"name": "sentiment", "status": "disabled", "detail": None})

        overall_ok = all(dep["status"] != "unavailable" for dep in dependencies if dep["name"] == "llm")
        return {"ok": overall_ok, "dependencies": dependencies}

    def stats_snapshot(self) -> dict[str, Any]:
        return self.stats.snapshot()

    def distill(self, request: Any) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/distill"
        started_at = datetime.now(timezone.utc)
        start = perf_counter()
        with _llm_guard("distill"):
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
        payload = DistillEndpointResponse(
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
        self._record_run(
            request_id=request_id,
            endpoint=endpoint,
            source=request.source,
            source_item_id=request.source_item_id,
            started_at=started_at,
            duration_ms=elapsed,
            input_chars=len(request.text),
            output_chars=_output_chars(payload),
            token_usage=usage,
            distill_prompt_version=self.settings.distill_prompt_version,
        )
        return payload

    def sentiment(self, request: SummaryRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/sentiment"
        started_at = datetime.now(timezone.utc)
        start = perf_counter()
        with _llm_guard("sentiment"):
            out, usage = sentiment.extract_sentiment(self.llm, request.summary)
        self.stats.mark_llm_success()
        elapsed = _ms(start)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, elapsed)
        payload = SentimentEndpointResponse(
            request_id=request_id,
            processing=ProcessingEnvelope(
                model=self.settings.llm_model,
                sentiment_prompt_version=self.settings.sentiment_prompt_version,
                token_usage=usage,
                durations_ms={"sentiment": elapsed, "total": elapsed},
            ),
            sentiment=out,
        ).model_dump(mode="json")
        self._record_run(
            request_id=request_id,
            endpoint=endpoint,
            source=request.source,
            source_item_id=request.source_item_id,
            started_at=started_at,
            duration_ms=elapsed,
            input_chars=len(request.summary),
            output_chars=_output_chars(payload),
            token_usage=usage,
            sentiment_prompt_version=self.settings.sentiment_prompt_version,
        )
        return payload

    def entities(self, request: SummaryRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/entities"
        started_at = datetime.now(timezone.utc)
        start = perf_counter()
        with _llm_guard("entities"):
            out, usage = entities.extract_entities(self.llm, request.summary)
        self.stats.mark_llm_success()
        items, warnings = self._enrich_entities(out.entities, request.options)
        elapsed = _ms(start)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, elapsed)
        payload = EntitiesEndpointResponse(
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
        self._record_run(
            request_id=request_id,
            endpoint=endpoint,
            source=request.source,
            source_item_id=request.source_item_id,
            started_at=started_at,
            duration_ms=elapsed,
            input_chars=len(request.summary),
            output_chars=_output_chars(payload),
            token_usage=usage,
            entity_prompt_version=self.settings.entity_prompt_version,
        )
        return payload

    def process(self, request: ProcessRequest) -> dict[str, Any]:
        request_id = str(uuid4())
        endpoint = "/v1/process"
        started_at = datetime.now(timezone.utc)
        started = perf_counter()
        total_usage: dict[str, int | float] = {}
        durations: dict[str, int] = {}
        warnings: list[str] = []

        distill_start = perf_counter()
        with _llm_guard("distill"):
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
            with _llm_guard("sentiment"):
                sentiment_out, sent_usage = sentiment.extract_sentiment(self.llm, distill_out.summary)
            self.stats.mark_llm_success()
            durations["sentiment"] = _ms(sent_start)
            _merge_usage(total_usage, sent_usage)
            self._deliver_sentiment(sentiment_out, request, warnings)

        entity_items = None
        if request.options.include_entities:
            ent_start = perf_counter()
            with _llm_guard("entities"):
                entity_out, ent_usage = entities.extract_entities(self.llm, distill_out.summary)
            self.stats.mark_llm_success()
            items, entity_warnings = self._enrich_entities(
                entity_out.entities,
                request.options,
                source=request.source,
                source_item_id=request.source_item_id,
                metadata=request.metadata,
            )
            warnings.extend(entity_warnings)
            durations["entities"] = _ms(ent_start)
            _merge_usage(total_usage, ent_usage)
            entity_items = {"items": items}

        durations["total"] = _ms(started)
        self.stats.increment("requests_total")
        self.stats.increment(f"requests:{endpoint}")
        self.stats.increment(f"success:{endpoint}")
        self.stats.record_latency(endpoint, durations["total"])

        payload = ProcessResponse(
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
        self._record_run(
            request_id=request_id,
            endpoint=endpoint,
            source=request.source,
            source_item_id=request.source_item_id,
            started_at=started_at,
            duration_ms=durations["total"],
            input_chars=len(request.text),
            output_chars=_output_chars(payload),
            token_usage=total_usage,
            distill_prompt_version=self.settings.distill_prompt_version,
            sentiment_prompt_version=(
                self.settings.sentiment_prompt_version if request.options.include_sentiment else None
            ),
            entity_prompt_version=(
                self.settings.entity_prompt_version if request.options.include_entities else None
            ),
        )
        return payload

    def _record_run(
        self,
        *,
        request_id: str,
        endpoint: str,
        source: str | None,
        source_item_id: str | None,
        started_at: datetime,
        duration_ms: int,
        input_chars: int,
        output_chars: int,
        token_usage: dict[str, Any],
        distill_prompt_version: str | None = None,
        sentiment_prompt_version: str | None = None,
        entity_prompt_version: str | None = None,
    ) -> None:
        if self.run_metrics is None:
            return
        try:
            self.run_metrics.record(
                request_id=request_id,
                endpoint=endpoint,
                source=source,
                source_item_id=source_item_id,
                model=self.settings.llm_model,
                distill_prompt_version=distill_prompt_version,
                sentiment_prompt_version=sentiment_prompt_version,
                entity_prompt_version=entity_prompt_version,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                duration_ms=duration_ms,
                input_chars=input_chars,
                output_chars=output_chars,
                token_usage=token_usage,
                status="succeeded",
            )
        except Exception:
            log.exception("run metrics write failed request_id=%s", request_id)

    def _enrich_entities(
        self,
        entity_rows: list[EntityMention],
        options: ProcessOptions,
        *,
        source: str | None = None,
        source_item_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[list[EnrichedEntity], list[str]]:
        warnings: list[str] = []
        enriched: list[EnrichedEntity] = []
        for row in entity_rows:
            watchlist_data = None
            if row.ticker and options.include_watchlist and self.watchlist is not None:
                try:
                    signal_id = self.watchlist.submit(
                        source=source or "quant_distill",
                        source_item_id=source_item_id or row.ticker,
                        ticker=row.ticker,
                        direction=row.direction,
                        confidence=row.confidence,
                        reason=row.context or "",
                        metadata={
                            **(metadata or {}),
                            "company_name": row.company_name,
                            "raw_mention": row.raw_mention,
                            "speaker": row.speaker,
                        },
                        model=self.settings.llm_model,
                        prompt_version=self.settings.entity_prompt_version,
                    )
                    watchlist_data = WatchlistEnrichment(entries=[{"signal_id": signal_id}])
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

    def _deliver_sentiment(
        self,
        output: Any,
        request: ProcessRequest,
        warnings: list[str],
    ) -> None:
        if self.sentiment_client is None:
            return
        observed_at = request.observed_at.isoformat() if request.observed_at else None
        for observation in output.observations:
            try:
                self.sentiment_client.deliver(
                    source=request.source,
                    source_item_id=request.source_item_id,
                    subject_type=observation.subject_type,
                    subject=observation.subject,
                    sentiment_label=observation.sentiment_label,
                    sentiment_score=observation.sentiment_score,
                    confidence=observation.confidence,
                    horizon=observation.horizon,
                    reason=observation.reason or "",
                    observed_at=observed_at,
                    metadata=request.metadata,
                    model=self.settings.llm_model,
                    prompt_version=self.settings.sentiment_prompt_version,
                )
            except Exception as exc:
                if self.settings.sentiment_required:
                    raise DependencyUnavailableError(
                        "dependency_unavailable",
                        "required dependency unavailable",
                        f"sentiment delivery failed: {type(exc).__name__}",
                    ) from exc
                warnings.append(f"sentiment delivery failed for {observation.subject}: {type(exc).__name__}")


def build_default_service() -> QuantDistillService:
    llm = OpenAICompatLLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout,
        max_tokens=settings.llm_max_tokens,
        json_mode=settings.llm_json_mode,
        num_ctx=settings.llm_num_ctx,
        retries=settings.http_retries,
        backoff=settings.retry_backoff,
    )
    watchlist = None
    if settings.signals_api_url:
        watchlist = WatchlistClient(
            base_url=settings.signals_api_url,
            api_key=settings.signals_api_key,
            timeout=settings.signals_timeout,
        )
    sentiment_client = None
    if settings.sentiment_api_url:
        sentiment_client = SentimentClient(
            url=settings.sentiment_api_url,
            api_key=settings.sentiment_api_key,
            timeout=settings.sentiment_timeout,
        )
    run_metrics = RunMetricsRepository(settings.database_url) if settings.database_url else None
    return QuantDistillService(
        llm_client=llm,
        watchlist_client=watchlist,
        sentiment_client=sentiment_client,
        run_metrics_repository=run_metrics,
    )
