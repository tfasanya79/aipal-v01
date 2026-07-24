from __future__ import annotations

from datetime import UTC, datetime, timedelta
import base64
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from sqlalchemy import select

from app.models import Goal, Memory, Reflection, Task
from app.services.companion_score_service import get_companion_score
from app.services.business_context_service import match_project_for_text
from app.services.memory_service import create_memory, extract_memories_from_message, persist_extracted_memories
from app.services.proactive_conversation_service import generate_proactive_prompt
from app.services.privacy_crypto import decrypt_value, encrypt_value
from app.services.relationship_followup_service import generate_followup_prompt


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_relationship_memory_extraction_types():
    event = extract_memories_from_message("I have a Qring demo tomorrow")
    concern = extract_memories_from_message("Nobody is buying")
    win = extract_memories_from_message("I closed my first estate customer")
    exhausted = extract_memories_from_message("I'm exhausted")
    praying = extract_memories_from_message("I've been praying more consistently")
    wife = extract_memories_from_message("My wife and I had a great conversation")

    assert any(item["type"] == "important_event" for item in event)
    assert any(item["type"] == "project" for item in event)
    assert any(item["follow_up_at"] is not None for item in event if item["type"] == "important_event")
    assert any(item["type"] == "recurring_concern" for item in concern)
    assert any(item["type"] == "win" for item in win)
    assert any(item["life_area"] == "health" for item in exhausted)
    assert any(item["life_area"] == "spiritual" for item in praying)
    assert any(item["type"] == "relationship" for item in wife)
    assert any(item["life_area"] == "relationships" for item in wife)


@pytest.mark.asyncio
async def test_low_confidence_memory_requires_confirmation_and_dedupes_semantically():
    low_confidence = extract_memories_from_message("My demo is tomorrow")
    assert any(
        item["type"] == "important_event" and item["requires_confirmation"]
        for item in low_confidence
    )

    client, headers, user_id = await _authed_client("dedupe@example.com")
    try:
        async with async_session() as db:
            created = await persist_extracted_memories(
                db,
                user_id,
                None,
                "I have a Qring demo tomorrow",
            )
            assert any(memory.type == "important_event" for memory in created)

            duplicate = await persist_extracted_memories(
                db,
                user_id,
                None,
                "My demo is tomorrow",
            )
            assert duplicate == []

            result = await db.execute(
                select(Memory).where(Memory.user_id == user_id, Memory.type == "important_event")
            )
            memories = result.scalars().all()
            assert len(memories) == 1
    finally:
        await client.aclose()


def test_privacy_crypto_uses_non_reversible_encryption():
    ciphertext = encrypt_value("super-secret")
    assert ciphertext is not None
    assert ciphertext != base64.urlsafe_b64encode(b"super-secret").decode("ascii")
    assert decrypt_value(ciphertext) == "super-secret"


@pytest.mark.asyncio
async def test_business_project_matching_requires_clear_context():
    client, headers, user_id = await _authed_client("project-match@example.com")
    try:
        async with async_session() as db:
            assert await match_project_for_text(db, user_id, "Qring") is None

            project = await match_project_for_text(db, user_id, "I have a Qring demo tomorrow")
            assert project is not None
            assert project.name == "Qring"

            result = await db.execute(
                select(Memory).where(Memory.user_id == user_id, Memory.type == "important_event")
            )
            memories = result.scalars().all()
            assert memories == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_followups_due_complete_and_dismiss():
    client, headers, user_id = await _authed_client("followups@example.com")
    try:
        async with async_session() as db:
            memory = await create_memory(
                db,
                user_id,
                type="important_event",
                life_area="business",
                title="Qring demo",
                content="User has a Qring demo tomorrow.",
                importance=8,
                follow_up_at=datetime.now(UTC) - timedelta(hours=1),
                follow_up_status="pending",
                follow_up_prompt="How did the Qring demo go?",
                event_date=datetime.now(UTC) - timedelta(days=1),
                entities=["Qring"],
                sentiment="neutral",
            )

        due = await client.get("/api/v2/relationship/followups/due", headers=headers)
        assert due.status_code == 200
        assert any(item["id"] == str(memory.id) for item in due.json())

        complete = await client.post(f"/api/v2/relationship/followups/{memory.id}/complete", headers=headers)
        assert complete.status_code == 200

        due_after = await client.get("/api/v2/relationship/followups/due", headers=headers)
        assert all(item["id"] != str(memory.id) for item in due_after.json())

        async with async_session() as db:
            memory2 = await create_memory(
                db,
                user_id,
                type="important_event",
                life_area="business",
                title="Demo follow-up",
                content="Need another check-in.",
                importance=7,
                follow_up_at=datetime.now(UTC) - timedelta(hours=1),
                follow_up_status="pending",
                follow_up_prompt="How did it go?",
                event_date=datetime.now(UTC) - timedelta(days=1),
            )
        dismiss = await client.post(f"/api/v2/relationship/followups/{memory2.id}/dismiss", headers=headers)
        assert dismiss.status_code == 200
        due_final = await client.get("/api/v2/relationship/followups/due", headers=headers)
        assert all(item["id"] != str(memory2.id) for item in due_final.json())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_proactive_prompt_uses_recent_relationship_context():
    client, headers, user_id = await _authed_client("proactive-context@example.com")
    try:
        async with async_session() as db:
            memory = await create_memory(
                db,
                user_id,
                type="recurring_concern",
                life_area="business",
                title="Concern about sales",
                content="Nobody is buying.",
                importance=8,
                sentiment="negative",
            )
            memory.created_at = datetime.now(UTC) - timedelta(days=1)
            await db.commit()

            prompt = await generate_proactive_prompt(db, user_id, force=True)
            assert prompt is not None
            assert prompt.prompt == "Structured proactive trigger ready."
            context = str((prompt.trigger_metadata or {}).get("context", "")).lower()
            assert "buying" in context or "sales" in context
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_memory_timeline_filters_and_user_isolation():
    client, headers, user_id = await _authed_client("timeline@example.com")
    other_client, other_headers, other_user_id = await _authed_client("timeline-other@example.com")
    try:
        async with async_session() as db:
            await create_memory(
                db,
                user_id,
                type="win",
                life_area="business",
                title="Closed first customer",
                content="Closed first estate customer.",
                importance=9,
                sentiment="positive",
                entities=["estate customer"],
            )
            await create_memory(
                db,
                user_id,
                type="failure",
                life_area="health",
                title="Missed workout",
                content="Missed workout after a long day.",
                importance=5,
                sentiment="negative",
            )
            await create_memory(
                db,
                other_user_id,
                type="win",
                life_area="business",
                title="Other user win",
                content="Other user memory.",
                importance=9,
            )

        timeline = await client.get("/api/v2/memory/timeline", headers=headers)
        assert timeline.status_code == 200
        items = timeline.json()["items"]
        assert all(item["type"] in {"win", "failure"} for item in items)
        assert all(item["life_area"] in {"business", "health"} for item in items)

        filtered = await client.get(
            "/api/v2/memory/timeline",
            headers=headers,
            params={"life_area": "business", "type": "win"},
        )
        assert filtered.status_code == 200
        filtered_items = filtered.json()["items"]
        assert len(filtered_items) == 1
        assert filtered_items[0]["title"] == "Closed first customer"
        assert all(item["title"] != "Other user win" for item in filtered_items)
        assert other_headers["Authorization"]
    finally:
        await client.aclose()
        await other_client.aclose()


@pytest.mark.asyncio
async def test_life_area_insights_and_companion_score():
    client, headers, user_id = await _authed_client("insights@example.com")
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Grow Qring", life_area="business", status="active", priority="high")
            db.add(goal)
            await db.commit()
            await db.refresh(goal)
            db.add(
                Task(
                    user_id=user_id,
                    title="Close a deal",
                    status="done",
                    goal_id=goal.id,
                    source="text",
                    category="business",
                )
            )
            db.add(
                Reflection(
                    user_id=user_id,
                    type="daily",
                    wins="Closed a deal",
                    challenges="Busy week",
                    lessons="Keep momentum",
                    mood="happy",
                    summary="Good week",
                )
            )
            await create_memory(
                db,
                user_id,
                type="win",
                life_area="business",
                title="Closed a deal",
                content="Closed a deal this week.",
                importance=9,
                sentiment="positive",
            )
            await db.commit()

        area = await client.get("/api/v2/insights/life-areas", headers=headers)
        assert area.status_code == 200
        areas = area.json()["areas"]
        assert any(item["life_area"] == "business" and item["memory_count"] >= 1 for item in areas)

        score = await client.get("/api/v2/insights/companion-score", headers=headers)
        assert score.status_code == 200
        score_body = score.json()
        assert score_body["overall"] is not None
        assert score_body["consistency"] is not None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_weekly_review_generation_and_latest():
    client, headers, user_id = await _authed_client("weekly@example.com")
    try:
        async with async_session() as db:
            await create_memory(
                db,
                user_id,
                type="win",
                life_area="business",
                title="Booked a Qring demo",
                content="Booked a Qring demo.",
                importance=8,
                sentiment="positive",
            )
            db.add(
                Reflection(
                    user_id=user_id,
                    type="daily",
                    wins="Kept moving",
                    challenges="Felt tired",
                    lessons="Rest matters",
                    mood="neutral",
                )
            )
            await db.commit()

        generated = await client.post("/api/v2/reflections/weekly/generate", headers=headers)
        assert generated.status_code == 200
        review = generated.json()
        assert review["summary"]
        assert review["type"] == "weekly"
        assert review["summary"].startswith("You made meaningful progress on")
        assert "Qring" in review["summary"]

        latest = await client.get("/api/v2/reflections/weekly/latest", headers=headers)
        assert latest.status_code == 200
        latest_body = latest.json()
        assert latest_body["id"] == review["id"]
        assert latest_body["type"] == "weekly"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_companion_turn_creates_relationship_memory_and_followup_context():
    client, headers, user_id = await _authed_client("companion-phase2@example.com")
    try:
        with (
            patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
            patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
        ):
            mock_llm.return_value = "I’m tracking that for you."
            turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I have a Qring demo tomorrow", "source": "text"},
            )
            assert turn.status_code == 200
            body = turn.json()
            assert body["reply"]
            assert body["suggested_actions"]

        async with async_session() as db:
            result = await db.execute(
                select(Memory).where(Memory.user_id == user_id, Memory.type == "important_event")
            )
            memory = result.scalar_one()
            assert memory.title == "Qring demo"
            assert memory.follow_up_at is not None
            assert generate_followup_prompt(memory) == "How did Qring demo go?"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_companion_turn_surfaces_due_followup_for_greeting():
    client, headers, user_id = await _authed_client("followup-greeting@example.com")
    try:
        async with async_session() as db:
            await create_memory(
                db,
                user_id,
                type="important_event",
                life_area="business",
                title="Qring demo",
                content="User has a Qring demo tomorrow.",
                importance=8,
                follow_up_at=datetime.now(UTC) - timedelta(hours=3),
                follow_up_status="pending",
                follow_up_prompt="How did the Qring demo go?",
                event_date=datetime.now(UTC) - timedelta(days=1),
                entities=["Qring"],
                sentiment="neutral",
            )

        with (
            patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
            patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
        ):
            mock_llm.return_value = "Hey"
            turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Hey", "source": "text"},
            )
            assert turn.status_code == 200
            body = turn.json()
            assert any(action["type"] == "follow_up" for action in body["suggested_actions"])

            prompt = mock_llm.call_args.args[0]
            context_prompt = prompt[1]["content"]
            assert "How did the Qring demo go?" in context_prompt
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_companion_score_returns_message_when_sparse():
    async with async_session() as db:
        score = await get_companion_score(db, uuid.uuid4())
    assert score["overall"] is None
    assert score["message"] == "Not enough data yet."
