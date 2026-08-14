from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, MetaData, String, Table, Column, create_engine
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
