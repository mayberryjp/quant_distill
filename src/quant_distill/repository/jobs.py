from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Integer,
    String,
    Table,
    and_,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from quant_distill.repository.run_metrics import metadata

QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"

_json = JSON().with_variant(JSONB, "postgresql")

jobs = Table(
    "jobs",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("job_id", String(36), nullable=False, unique=True, index=True),
    Column("endpoint", String(32), nullable=False),
    Column("status", String(16), nullable=False),
    Column("source", String(64)),
    Column("source_item_id", String(256)),
    Column("request", _json, nullable=False),
    Column("result", _json),
    Column("error", String(512)),
    Column("attempts", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class JobsRepository:
    def __init__(self, database_url: str, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def enqueue(
        self,
        *,
        endpoint: str,
        request: dict[str, Any],
        source: str | None = None,
        source_item_id: str | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid4())
        created_at = _now()
        with self.engine.begin() as connection:
            connection.execute(
                jobs.insert().values(
                    job_id=job_id,
                    endpoint=endpoint,
                    status=QUEUED,
                    source=source,
                    source_item_id=source_item_id,
                    request=request,
                    attempts=0,
                    created_at=created_at,
                )
            )
        return {"job_id": job_id, "status": QUEUED, "created_at": created_at}

    def claim(self) -> dict[str, Any] | None:
        # SKIP LOCKED lets multiple workers/replicas pull distinct jobs safely.
        candidate = (
            select(jobs.c.id)
            .where(jobs.c.status == QUEUED)
            .order_by(jobs.c.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        statement = (
            jobs.update()
            .where(jobs.c.id == candidate)
            .values(status=RUNNING, started_at=_now(), attempts=jobs.c.attempts + 1)
            .returning(*jobs.c)
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().first()
        return dict(row) if row else None

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                jobs.update()
                .where(jobs.c.job_id == job_id)
                .values(status=SUCCEEDED, result=result, error=None, completed_at=_now())
            )

    def fail(self, job_id: str, error: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                jobs.update()
                .where(jobs.c.job_id == job_id)
                .values(status=FAILED, error=error[:512], completed_at=_now())
            )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(jobs.select().where(jobs.c.job_id == job_id)).mappings().first()
        return dict(row) if row else None

    def list_jobs(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        source_item_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        filters = []
        if status:
            filters.append(jobs.c.status == status)
        if source:
            filters.append(jobs.c.source == source)
        if source_item_id:
            filters.append(jobs.c.source_item_id == source_item_id)

        order_by = jobs.c.id.asc() if order == "asc" else jobs.c.id.desc()
        query = jobs.select().order_by(order_by).limit(limit).offset(offset)
        count_query = select(func.count()).select_from(jobs)
        if filters:
            query = query.where(and_(*filters))
            count_query = count_query.where(and_(*filters))

        with self.engine.connect() as connection:
            rows = [dict(row) for row in connection.execute(query).mappings()]
            total = connection.execute(count_query).scalar_one()
        return rows, int(total)

    def counts_by_status(self) -> dict[str, int]:
        query = select(jobs.c.status, func.count()).group_by(jobs.c.status)
        with self.engine.connect() as connection:
            return {status: int(count) for status, count in connection.execute(query)}

    def requeue_stale_running(self) -> int:
        """Reset jobs left RUNNING by a crashed process so they are picked up again."""
        statement = jobs.update().where(jobs.c.status == RUNNING).values(status=QUEUED, started_at=None)
        with self.engine.begin() as connection:
            return int(connection.execute(statement).rowcount or 0)

    def readiness(self) -> tuple[bool, str]:
        try:
            with self.engine.connect() as connection:
                connection.execute(select(func.count()).select_from(jobs)).scalar_one()
            return True, "ok"
        except Exception as exc:
            return False, type(exc).__name__

    def close(self) -> None:
        self.engine.dispose()
