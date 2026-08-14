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


def run_migrations_online() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")

    connectable = create_engine(database_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table="quant_distill_alembic_version",
            version_table_schema=SCHEMA_NAME,
        )
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
