"""Create quant_distill run metrics.

Revision ID: 0001_run_metrics
Revises:
Create Date: 2026-08-14
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_run_metrics"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_NAME = "quant_distill"


def upgrade() -> None:
    op.create_table(
        "run_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("endpoint", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64)),
        sa.Column("source_item_id", sa.String(length=256)),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("distill_prompt_version", sa.String(length=64)),
        sa.Column("sentiment_prompt_version", sa.String(length=64)),
        sa.Column("entity_prompt_version", sa.String(length=64)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("output_chars", sa.Integer(), nullable=False),
        sa.Column("token_usage", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_type", sa.String(length=128)),
        schema=SCHEMA_NAME,
    )
    op.create_index("ix_quant_distill_run_metrics_request_id", "run_metrics", ["request_id"], schema=SCHEMA_NAME)


def downgrade() -> None:
    op.drop_index("ix_quant_distill_run_metrics_request_id", table_name="run_metrics", schema=SCHEMA_NAME)
    op.drop_table("run_metrics", schema=SCHEMA_NAME)
