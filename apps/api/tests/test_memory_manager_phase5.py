from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from types import SimpleNamespace

from app.db import async_session
from app.models import (
    BusinessProject,
    CalendarEventCache,
    Goal,
    KnowledgeEntity,
    Memory,
    MemorySearchDocument,
    Message,
    Reminder,
    Task,
    TodayItem,
    User,
    Conversation,
)
from app.services.embedding_service import embed_text
from app.services import embedding_service
from app.services.memory_manager import MemoryManager
from app.conversation.adapters import LegacyCompanionBrainAdapter
from app.conversation.contracts import ConversationInput, InputModality, OrchestrationContext


async def _embed(text: str) -> list[float]:
    return embed_text(text)


async def _user(db, suffix: str) -> User:
    row = User(email=f"phase5-{suffix}-{uuid.uuid4()}@example.com", timezone="UTC")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@pytest.mark.asyncio
async def test_stable_retrieval_covers_required_live_domains():
    async with async_session() as db:
        user = await _user(db, "stable")
        now = datetime.now(UTC)
        project = BusinessProject(user_id=user.id, name="Atlas", description="Migration program")
        person = KnowledgeEntity(user_id=user.id, entity_type="person", name="Ada", description="Design lead")
        relationship = KnowledgeEntity(user_id=user.id, entity_type="relationship", name="Mentor", description="Career mentor")
        goal = Goal(user_id=user.id, title="Ship Atlas", status="active", priority="high")
        task = Task(user_id=user.id, title="Review launch plan", status="planned", due_at=now + timedelta(hours=1))
        reminder = Reminder(user_id=user.id, title="Call Ada", remind_at=now + timedelta(hours=2), status="scheduled")
        calendar = CalendarEventCache(user_id=user.id, external_id="cal-1", title="Atlas review", starts_at=now + timedelta(hours=1))
        today = TodayItem(user_id=user.id, type="focus", title="Atlas focus", start_time=now + timedelta(hours=3))
        memory = Memory(user_id=user.id, type="project", title="Atlas constraint", content="Budget is fixed", importance=5, approval_status="approved")
        conversation = Conversation(user_id=user.id, mode="companion")
        db.add_all([project, person, relationship, goal, task, reminder, calendar, today, memory, conversation])
        await db.commit()
        message = Message(user_id=user.id, conversation_id=conversation.id, role="user", content="We discussed launch risk")
        db.add(message)
        await db.commit()

        stable = await MemoryManager(_embed).retrieve_stable(db, user, conversation_id=conversation.id)

        assert {item["title"] for item in stable["projects"]} == {"Atlas"}
        assert {item["title"] for item in stable["people"]} == {"Ada", "Mentor"}
        assert stable["goals"][0]["title"] == "Ship Atlas"
        assert stable["tasks"][0]["title"] == "Review launch plan"
        assert stable["reminders"][0]["title"] == "Call Ada"
        assert stable["calendar"][0]["title"] == "Atlas review"
        assert stable["today"][0]["title"] == "Atlas focus"
        assert stable["long_term_memory"][0]["title"] == "Atlas constraint"
        assert stable["recent_discussions"][0]["content"] == "We discussed launch risk"


@pytest.mark.asyncio
async def test_query_retrieval_uses_bounded_vector_candidates_across_domains():
    async with async_session() as db:
        user = await _user(db, "query")
        manager = MemoryManager(_embed)
        old_relevant = Memory(
            user_id=user.id,
            type="decision",
            title="Quarterly launch decision",
            content="Quarterly launch uses the blue rollout plan",
            importance=5,
            approval_status="approved",
            created_at=datetime.now(UTC) - timedelta(days=300),
            updated_at=datetime.now(UTC) - timedelta(days=300),
        )
        db.add(old_relevant)
        for index in range(220):
            db.add(Memory(user_id=user.id, type="note", title=f"Noise {index}", content=f"unrelated item {index}", approval_status="approved"))
        project = BusinessProject(user_id=user.id, name="Blue rollout", description="Quarterly launch delivery")
        db.add(project)
        await db.commit()
        await manager.backfill_user(db, user.id)

        result = await manager.retrieve_query(db, user.id, "quarterly launch blue rollout", limit=8)

        titles = {item["title"] for item in result["items"]}
        assert "Quarterly launch decision" in titles
        assert "Blue rollout" in titles
        assert result["metrics"]["candidate_count"] <= 160
        assert result["metrics"]["backend"] == "lsh_cosine"


@pytest.mark.asyncio
async def test_index_update_and_delete_do_not_leave_stale_documents():
    async with async_session() as db:
        user = await _user(db, "lifecycle")
        manager = MemoryManager(_embed)
        task = Task(user_id=user.id, title="Original task", status="planned")
        db.add(task)
        await db.commit()
        await db.refresh(task)

        await manager.index_row(db, task)
        task.title = "Updated task"
        task.updated_at = datetime.now(UTC)
        await db.commit()
        await manager.index_row(db, task)

        rows = (await db.execute(select(MemorySearchDocument).where(
            MemorySearchDocument.user_id == user.id,
            MemorySearchDocument.source_type == "task",
            MemorySearchDocument.source_id == str(task.id),
        ))).scalars().all()
        assert len(rows) == 1
        assert rows[0].title == "Updated task"

        await manager.delete_source(db, user.id, "task", str(task.id))
        remaining = (await db.execute(select(MemorySearchDocument).where(
            MemorySearchDocument.user_id == user.id,
            MemorySearchDocument.source_type == "task",
            MemorySearchDocument.source_id == str(task.id),
        ))).scalars().all()
        assert remaining == []


@pytest.mark.asyncio
async def test_merge_deduplicates_stable_and_query_specific_context():
    stable = {
        "tasks": [{"id": "1", "source_type": "task", "title": "Plan"}],
        "today": [], "calendar": [], "reminders": [], "long_term_memory": [],
        "recent_discussions": [], "goals": [], "projects": [], "people": [],
        "metrics": {"stable_retrieval_ms": 3},
    }
    query = {
        "items": [
            {"id": "1", "source_type": "task", "title": "Plan"},
            {"id": "2", "source_type": "memory", "title": "Decision"},
        ],
        "metrics": {"query_retrieval_ms": 4},
    }
    merged = MemoryManager.merge(stable, query)
    assert len(merged["tasks"]) == 1
    assert merged["memories"][0]["title"] == "Decision"
    assert merged["metrics"] == {"stable_retrieval_ms": 3, "query_retrieval_ms": 4}


@pytest.mark.asyncio
async def test_unified_adapter_forwards_speech_preload_to_the_same_brain(monkeypatch):
    captured = {}

    class FakeCompanion:
        async def run_turn_stream(self, _db, _user, _text, **kwargs):
            captured.update(kwargs)
            yield {
                "type": "context_ready",
                "mode": "companion",
                "metrics": {"stable_retrieval_ms": 2},
            }
            yield {"type": "reply_delta", "text": "ok"}
            yield {"type": "speech_segment_ready", "text": "ok"}
            yield {"type": "turn_complete", "reply": "ok", "mode": "companion"}

    monkeypatch.setattr("app.conversation.adapters.get_companion_orchestrator", lambda: FakeCompanion())
    user_id = uuid.uuid4()
    request = ConversationInput(user_id=user_id, modality=InputModality.LIVE_VOICE, text="final transcript")
    context = OrchestrationContext(
        db=object(),
        user=SimpleNamespace(id=user_id),
        preloaded_context={"_stable_memory": {"projects": [{"id": "p1"}]}},
    )
    events = [event async for event in LegacyCompanionBrainAdapter().stream(request, context)]

    assert captured["source_context"]["preloaded_context"] == context.preloaded_context
    assert events[0]["type"] == "context_ready"
    assert events[-1]["type"] == "turn_complete"


@pytest.mark.asyncio
async def test_retrieval_latency_stays_bounded_with_large_index():
    async with async_session() as db:
        user = await _user(db, "latency")
        manager = MemoryManager(_embed)
        for index in range(400):
            row = Memory(
                user_id=user.id,
                type="note",
                title=f"Indexed note {index}",
                content=f"topic-{index % 25} context and decision {index}",
                approval_status="approved",
            )
            db.add(row)
        await db.commit()
        await manager.backfill_user(db, user.id)

        samples = []
        for _ in range(12):
            started = datetime.now(UTC)
            result = await manager.retrieve_query(db, user.id, "topic-7 context decision", limit=10)
            samples.append((datetime.now(UTC) - started).total_seconds() * 1000)
            assert result["metrics"]["candidate_count"] <= 160
        samples.sort()
        p95 = samples[int(len(samples) * 0.95) - 1]
        assert p95 < 150, f"query retrieval p95 {p95:.2f}ms exceeded 150ms"

        async def loaded_query() -> int:
            async with async_session() as load_db:
                result = await manager.retrieve_query(
                    load_db, user.id, "topic-7 context decision", limit=10
                )
                return int(result["metrics"]["query_retrieval_ms"])

        concurrent = await asyncio.gather(*(loaded_query() for _ in range(20)))
        assert max(concurrent) < 500


@pytest.mark.asyncio
async def test_vector_retrieval_is_strictly_user_scoped():
    async with async_session() as db:
        first = await _user(db, "isolation-a")
        second = await _user(db, "isolation-b")
        manager = MemoryManager(_embed)
        first_memory = Memory(user_id=first.id, type="fact", title="Private Atlas", content="secret atlas detail", approval_status="approved")
        second_memory = Memory(user_id=second.id, type="fact", title="Private Beacon", content="secret beacon detail", approval_status="approved")
        db.add_all([first_memory, second_memory])
        await db.commit()
        await manager.index_row(db, first_memory)
        await manager.index_row(db, second_memory)

        result = await manager.retrieve_query(db, first.id, "secret beacon detail", limit=10)
        assert all(item["title"] != "Private Beacon" for item in result["items"])


@pytest.mark.asyncio
async def test_query_retrieval_excludes_temporary_memory_that_expired_after_indexing():
    async with async_session() as db:
        user = await _user(db, "expiry")
        manager = MemoryManager(_embed)
        memory = Memory(
            user_id=user.id,
            type="temporary",
            title="Short-lived secret",
            content="ephemeral launch code",
            approval_status="approved",
            memory_scope="temporary",
            expires_at=datetime.now(UTC) + timedelta(milliseconds=50),
        )
        db.add(memory)
        await db.commit()
        await manager.index_row(db, memory)
        await asyncio.sleep(0.1)

        result = await manager.retrieve_query(
            db, user.id, "ephemeral launch code", limit=10
        )

        assert all(item["id"] != str(memory.id) for item in result["items"])


@pytest.mark.asyncio
async def test_production_embedding_failure_is_fail_closed(monkeypatch):
    settings = SimpleNamespace(
        embedding_provider="unsupported",
        embedding_model="none",
        embedding_timeout_seconds=0.1,
        aipal_env="production",
        openai_api_key="",
        openai_base_url="",
        ollama_base_url="",
    )
    monkeypatch.setattr(embedding_service, "get_settings", lambda: settings)
    with pytest.raises(RuntimeError, match="Semantic embedding provider"):
        await embedding_service.embed_text_semantic("production memory")
