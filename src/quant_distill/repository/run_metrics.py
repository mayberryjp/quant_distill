from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

SCHEMA_NAME = "quant_distill"

metadata = MetaData(schema=SCHEMA_NAME)
run_metrics = Table(
    "run_metrics",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("request_id", String(36), nullable=False, index=True),
    Column("endpoint", String(32), nullable=False),
    Column("source", String(64)),
    Column("source_item_id", String(256)),
    Column("model", String(128), nullable=False),
    Column("distill_prompt_version", String(64)),
    Column("sentiment_prompt_version", String(64)),
    Column("entity_prompt_version", String(64)),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=False),
    Column("duration_ms", Integer, nullable=False),
    Column("input_chars", Integer, nullable=False),
    Column("output_chars", Integer, nullable=False),
    Column("token_usage", JSON().with_variant(JSONB, "postgresql"), nullable=False),
    Column("status", String(16), nullable=False),
    Column("error_type", String(128)),
)


class RunMetricsRepository:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def record(
        self,
        *,
        request_id: str,
        endpoint: str,
        source: str | None,
        source_item_id: str | None,
        model: str,
        distill_prompt_version: str | None,
        sentiment_prompt_version: str | None,
        entity_prompt_version: str | None,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: int,
        input_chars: int,
        output_chars: int,
        token_usage: dict[str, Any],
        status: str,
        error_type: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                run_metrics.insert().values(
                    request_id=request_id,
                    endpoint=endpoint,
                    source=source,
                    source_item_id=source_item_id,
                    model=model,
                    distill_prompt_version=distill_prompt_version,
                    sentiment_prompt_version=sentiment_prompt_version,
                    entity_prompt_version=entity_prompt_version,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    input_chars=input_chars,
                    output_chars=output_chars,
                    token_usage=token_usage,
                    status=status,
                    error_type=error_type,
                )
            )

    def close(self) -> None:
        self.engine.dispose()

    def readiness(self) -> tuple[bool, str]:
        try:
            with self.engine.connect() as connection:
                connection.execute(select(func.count()).select_from(run_metrics)).scalar_one()
            return True, "ok"
        except Exception as exc:
            return False, type(exc).__name__

    def list_runs(
        self,
        *,
        source: str | None = None,
        endpoint: str | None = None,
        status: str | None = None,
        source_item_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        filters = []
        if source:
            filters.append(run_metrics.c.source == source)
        if endpoint:
            filters.append(run_metrics.c.endpoint == endpoint)
        if status:
            filters.append(run_metrics.c.status == status)
        if source_item_id:
            filters.append(run_metrics.c.source_item_id == source_item_id)
        if since:
            filters.append(run_metrics.c.started_at >= since)
        if until:
            filters.append(run_metrics.c.started_at <= until)

        order_by = run_metrics.c.started_at.asc() if order == "asc" else run_metrics.c.started_at.desc()
        query = run_metrics.select().order_by(order_by, run_metrics.c.id.desc()).limit(limit).offset(offset)
        count_query = select(func.count()).select_from(run_metrics)
        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(query).mappings()]
            total = connection.execute(count_query).scalar_one()
        return rows, int(total)

    def get_run(self, request_id: str) -> dict[str, Any] | None:
        query = run_metrics.select().where(run_metrics.c.request_id == request_id)
        with self.engine.connect() as connection:
            row = connection.execute(query).mappings().first()
        return dict(row) if row else None
