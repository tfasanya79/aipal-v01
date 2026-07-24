from __future__ import annotations

import json
import os
import statistics
import time
import uuid

import pytest
from sqlalchemy import delete, text

from app.db import async_session
from app.models import Memory, MemoryIndexStatus, MemorySearchDocument, User
from app.services.embedding_service import embed_text
from app.services.memory_manager import MemoryManager


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_PHASE5_TESTS") != "1",
    reason="set RUN_POSTGRES_PHASE5_TESTS=1 against an isolated pgvector database",
)


async def _embed(value: str) -> list[float]:
    return embed_text(value)


def _plan_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str)


@pytest.mark.asyncio(loop_scope="session")
async def test_phase5_pgvector_hnsw_backfill_retrieval_and_latency():
    manager = MemoryManager(_embed)
    user_id = uuid.uuid4()
    query = "topic-7 launch decision"

    async with async_session() as db:
        user = User(id=user_id, email=f"phase5-pg-{user_id}@example.com", timezone="UTC")
        db.add(user)
        await db.commit()
        for index in range(400):
            db.add(
                Memory(
                    user_id=user_id,
                    type="decision",
                    title=f"Indexed decision {index}",
                    content=f"topic-{index % 25} launch decision context {index}",
                    approval_status="approved",
                )
            )
        await db.commit()

        try:
            indexed = await manager.backfill_user(db, user_id, force=True)
            assert indexed == 400

            # Phase 5's production budget is explicitly measured with the
            # embedding/ranking runtime warm; image-build verification covers
            # cold model provisioning separately.
            await manager.retrieve_query(db, user_id, query, limit=10)
            samples_ms: list[float] = []
            result = None
            for _ in range(12):
                started = time.perf_counter()
                result = await manager.retrieve_query(db, user_id, query, limit=10)
                samples_ms.append((time.perf_counter() - started) * 1_000)

            assert result is not None
            assert result["metrics"]["backend"] == "pgvector"
            assert result["metrics"]["candidate_count"] <= 40
            assert result["items"]
            p95 = statistics.quantiles(samples_ms, n=20)[18]
            assert p95 < 250, f"pgvector query p95 {p95:.2f}ms exceeds 250ms"

            vector = await _embed(query)
            vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
            await db.execute(text("SET LOCAL enable_seqscan = off"))
            # A 400-row, single-user fixture is legitimately cheaper to serve
            # through the user_id B-tree plus an in-memory sort. Disable that
            # plan only for this compatibility assertion to prove PostgreSQL
            # can execute the production query through the HNSW index.
            await db.execute(text("SET LOCAL enable_sort = off"))
            plan = (
                await db.execute(
                    text(
                        "EXPLAIN (FORMAT JSON) "
                        "SELECT id FROM memory_search_documents "
                        "WHERE user_id = :user_id "
                        "ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT 40"
                    ),
                    {"user_id": user_id, "embedding": vector_literal},
                )
            ).scalar_one()
            assert "ix_memory_search_documents_embedding_hnsw" in _plan_text(plan)
        finally:
            await db.rollback()
            await db.execute(
                delete(MemorySearchDocument).where(
                    MemorySearchDocument.user_id == user_id
                )
            )
            await db.execute(
                delete(MemoryIndexStatus).where(MemoryIndexStatus.user_id == user_id)
            )
            await db.execute(delete(Memory).where(Memory.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
