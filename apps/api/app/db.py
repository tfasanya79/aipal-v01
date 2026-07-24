from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()


def _engine_kwargs(url: str) -> dict:
    if ":memory:" in url:
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    if url.startswith("sqlite+aiosqlite://"):
        return {
            "poolclass": NullPool,
        }
    return {}


engine = create_async_engine(settings.database_url, echo=False, **_engine_kwargs(settings.database_url))
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            try:
                await conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:
                # Local tests often run on SQLite and production deployments may
                # provision pgvector separately; table creation should still continue.
                pass
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            # create_all does not add columns to existing local databases. This
            # keeps dev DBs that were stamped at head before older migrations ran
            # aligned with the current models without touching complete schemas.
            await conn.exec_driver_sql(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS updated_at "
                "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS updated_at "
                "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS goal_id UUID NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS parent_task_id INTEGER NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS estimated_minutes INTEGER NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS category VARCHAR(32) NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE tasks "
                "ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE messages "
                "ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT 'text'"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE reflections "
                "ADD COLUMN IF NOT EXISTS goal_id UUID NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE reflections "
                "ADD COLUMN IF NOT EXISTS summary TEXT NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE reflections "
                "ADD COLUMN IF NOT EXISTS metadata JSON NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE reflections "
                "ADD COLUMN IF NOT EXISTS score JSON NULL"
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_goal_id ON tasks (goal_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_tasks_parent_task_id ON tasks (parent_task_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_reflections_goal_id ON reflections (goal_id)")
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS approval_status VARCHAR(32) NOT NULL DEFAULT 'approved'"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS memory_scope VARCHAR(32) NOT NULL DEFAULT 'permanent'"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS suggested_reason TEXT NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS edited_from_id UUID NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS source_message_id UUID NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS follow_up_at TIMESTAMP WITH TIME ZONE NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS follow_up_status VARCHAR(32) NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE proactive_prompts "
                "ADD COLUMN IF NOT EXISTS trigger_metadata JSON NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS follow_up_prompt TEXT NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS event_date TIMESTAMP WITH TIME ZONE NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS entities JSONB NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS sentiment VARCHAR(32) NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS sensitive BOOLEAN NOT NULL DEFAULT FALSE"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS user_approved BOOLEAN NOT NULL DEFAULT TRUE"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS paused BOOLEAN NOT NULL DEFAULT FALSE"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS source_provider VARCHAR(64) NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE user_companion_preferences "
                "ADD COLUMN IF NOT EXISTS tts_voice VARCHAR(64) NOT NULL DEFAULT 'default'"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS source_item_id UUID NULL"
            )
            await conn.exec_driver_sql(
                "ALTER TABLE memories "
                "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_memories_source_message_id ON memories (source_message_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_memories_edited_from_id ON memories (edited_from_id)")
