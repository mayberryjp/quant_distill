"""Create quant_distill async job queue.

Revision ID: 0002_jobs
Revises: 0001_run_metrics
Create Date: 2026-08-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_jobs"
down_revision = "0001_run_metrics"
branch_labels = None
depends_on = None

SCHEMA_NAME = "quant_distill"


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=36), nullable=False, unique=True),
        sa.Column("endpoint", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=64)),
        sa.Column("source_item_id", sa.String(length=256)),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("error", sa.String(length=512)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema=SCHEMA_NAME,
    )
    op.create_index("ix_quant_distill_jobs_job_id", "jobs", ["job_id"], schema=SCHEMA_NAME)
    # Partial index keeps the claim query cheap as completed jobs accumulate.
    op.create_index(
        "ix_quant_distill_jobs_queued",
        "jobs",
        ["id"],
        schema=SCHEMA_NAME,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_quant_distill_jobs_source_item",
        "jobs",
        ["source", "source_item_id"],
        schema=SCHEMA_NAME,
    )


def downgrade() -> None:
    op.drop_index("ix_quant_distill_jobs_source_item", table_name="jobs", schema=SCHEMA_NAME)
    op.drop_index("ix_quant_distill_jobs_queued", table_name="jobs", schema=SCHEMA_NAME)
    op.drop_index("ix_quant_distill_jobs_job_id", table_name="jobs", schema=SCHEMA_NAME)
    op.drop_table("jobs", schema=SCHEMA_NAME)
