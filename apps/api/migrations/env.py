from __future__ import annotations

import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app import models as _models  # noqa: F401,E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
target_metadata = Base.metadata
def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    if connection.dialect.name == "postgresql":
        # The baseline migration already contains vector columns, so pgvector
        # must exist before Alembic executes revision 0001. Creating it only in
        # the Phase 5 revision is too late for a clean production database.
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        # End SQLAlchemy's implicit transaction so Alembic owns and commits the
        # migration transaction instead of having it rolled back on close.
        connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = settings.database_url
    engine_config = {"sqlalchemy.url": url}
    connectable = async_engine_from_config(
        engine_config,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    except Exception:
        await connectable.dispose()
        # Deployment migrations must fail closed. Falling back to an unrelated
        # SQLite file can make Alembic exit successfully while PostgreSQL is
        # unchanged, producing a false production-readiness signal.
        raise
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
