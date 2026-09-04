from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

from quant_distill.repository.run_metrics import SCHEMA_NAME, metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata
VERSION_TABLE = "alembic_version_distill"
LEGACY_SCHEMA_NAME = "quant_distill"


def _relocate_legacy_tables(connection) -> None:
    """Ensure the distill schema exists, move any tables still living in the
    legacy schema (including the alembic version table) into it, then drop the
    now-empty legacy schema."""
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
    legacy_tables = (
        connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = :schema"),
            {"schema": LEGACY_SCHEMA_NAME},
        )
        .scalars()
        .all()
    )
    for table_name in legacy_tables:
        connection.execute(
            text(f'ALTER TABLE {LEGACY_SCHEMA_NAME}."{table_name}" SET SCHEMA {SCHEMA_NAME}')
        )
    # Tables were moved (not dropped), so their data persists; drop the emptied schema.
    connection.execute(text(f"DROP SCHEMA IF EXISTS {LEGACY_SCHEMA_NAME} RESTRICT"))
    connection.commit()


def run_migrations_online() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")

    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        _relocate_legacy_tables(connection)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table=VERSION_TABLE,
            version_table_schema=SCHEMA_NAME,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
