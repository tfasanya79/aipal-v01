from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from app.models import Task

from app.main import app
from app.services.emotion_service import detect_emotion
from app.models import AuditLog
from app.services.memory_service import (
    approve_memory,
    create_memory,
    delete_memory,
    export_memories,
    extract_memories_from_message,
    recent_life_area_insight,
    search_memories,
    update_memory,
)
from app.services.mode_router import classify_mode


def test_mode_router_and_emotion_detection():
    assert classify_mode("plan my day tomorrow", "neutral") == "planner"
    assert classify_mode("remind me to call mom", "neutral") == "assistant"
    assert classify_mode("I feel stuck and confused", "confused") == "companion"
    assert classify_mode("What should I choose?", "neutral") == "coach"
    assert classify_mode("wins lessons and mood", "happy") == "reflection"
    assert classify_mode("What did I learn today?", "neutral") == "reflection"
    assert classify_mode("I'm tired today.", "neutral") == "companion"
    assert classify_mode("Nobody is buying.", "frustrated") in {"companion", "coach"}

    emo = detect_emotion("I am exhausted and burned out")
    assert emo["emotion"] == "burned_out"
    assert 1 <= int(emo["intensity"]) <= 10


def test_life_area_extraction_assigns_business_and_personal():
    business_memory = extract_memories_from_message(
        "I need to launch the product and follow up with clients this week",
    )[0]
    assert business_memory["life_area"] == "business"

    personal_memory = extract_memories_from_message("I have been feeling emotionally drained lately")[0]
    assert personal_memory["life_area"] == "personal"


@pytest.mark.asyncio
async def test_companion_turn_returns_mode_emotion_and_sensitive_memory_prompt():
    transport = ASGITransport(app=app)
    with (
        patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
    ):
        mock_llm.return_value = "That sounds heavy. I’m here with you."
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "companion@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

            r = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I was diagnosed with diabetes yesterday", "source": "text"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["reply"]
            assert body["mode"] in {"companion", "coach"}
            assert body["emotion"]["emotion"] in {"sad", "anxious", "frustrated", "neutral", "burned_out"}
            assert body["requires_confirmation"] is True
            assert body["confirmation_prompt"]
            assert body["conversation_id"]


@pytest.mark.asyncio
async def test_sensitive_memory_can_be_approved_or_denied():
    transport = ASGITransport(app=app)
    with (
        patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
    ):
        mock_llm.return_value = "Thanks for trusting me."
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "sensitive@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

            turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "My diagnosis is private", "source": "text"},
            )
            assert turn.status_code == 200
            assert turn.json()["requires_confirmation"] is True

            memories = await client.get("/api/v2/memory", headers=headers)
            assert memories.status_code == 200
            memory_row = next(item for item in memories.json() if item["title"] == "My diagnosis is private")
            memory_id = memory_row["id"]
            assert memory_row["user_approved"] is False

            approve = await client.post(f"/api/v2/memory/{memory_id}/approve", headers=headers)
            assert approve.status_code == 200

            memories_after = await client.get("/api/v2/memory", headers=headers)
            assert any(item["id"] == memory_id and item["user_approved"] is True for item in memories_after.json())

            deny = await client.post(f"/api/v2/memory/{memory_id}/deny", headers=headers)
            assert deny.status_code == 200

            memories_final = await client.get("/api/v2/memory", headers=headers)
            assert all(item["id"] != memory_id for item in memories_final.json())


@pytest.mark.asyncio
async def test_memory_actions_are_audited():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "audit@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        user_id = uuid.UUID(verify.json()["user_id"])

        from app.db import async_session

        async with async_session() as db:
            memory = await create_memory(
                db,
                user_id,
                type="fact",
                life_area="business",
                title="Audit note",
                content="Audit note for memory tracking.",
            )
            await update_memory(db, user_id, memory.id, {"title": "Audit note updated"})
            await export_memories(db, user_id)
            await approve_memory(db, user_id, memory.id)

            memory2 = await create_memory(
                db,
                user_id,
                type="fact",
                life_area="personal",
                title="Audit delete",
                content="Delete me",
            )
            await delete_memory(db, user_id, memory2.id)

            result = await db.execute(
                select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.created_at.asc())
            )
            actions = [row.action for row in result.scalars().all()]

        assert "memory.create" in actions
        assert "memory.update" in actions
        assert "memory.export" in actions
        assert "memory.approve" in actions
        assert "memory.delete" in actions


@pytest.mark.asyncio
async def test_memory_search_is_scoped_per_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg1 = await client.post("/api/v2/auth/register", json={"email": "user1@example.com"})
        verify1 = await client.post("/api/v2/auth/verify", json={"token": reg1.json()["dev_token"]})
        reg2 = await client.post("/api/v2/auth/register", json={"email": "user2@example.com"})
        verify2 = await client.post("/api/v2/auth/verify", json={"token": reg2.json()["dev_token"]})

        from app.db import async_session

        user1_id = uuid.UUID(verify1.json()["user_id"])
        user2_id = uuid.UUID(verify2.json()["user_id"])

        async with async_session() as db:
            await create_memory(
                db,
                user1_id,
                type="fact",
                life_area="business",
                title="Project Alpha",
                content="User one is building Project Alpha",
            )
            await create_memory(
                db,
                user2_id,
                type="fact",
                life_area="business",
                title="Project Beta",
                content="User two is building Project Beta",
            )

            found_user1 = await search_memories(db, user1_id, "Project Alpha", limit=5)
            found_user2 = await search_memories(db, user2_id, "Project Beta", limit=5)

        assert any(memory.title == "Project Alpha" for memory in found_user1)
        assert all(memory.title != "Project Beta" for memory in found_user1)
        assert any(memory.title == "Project Beta" for memory in found_user2)


@pytest.mark.asyncio
async def test_memory_search_prefers_goal_related_context():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "ranking@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        user_id = uuid.UUID(verify.json()["user_id"])

        from app.db import async_session

        async with async_session() as db:
            await create_memory(
                db,
                user_id,
                type="goal",
                life_area="business",
                title="Launch landing page",
                content="We need to launch the landing page this week.",
            )
            await create_memory(
                db,
                user_id,
                type="fact",
                life_area="personal",
                title="Weekend note",
                content="Went for a walk and rested.",
            )

            ranked = await search_memories(
                db,
                user_id,
                "launch",
                limit=5,
                goal_titles=["Launch landing page"],
                recent_summary="We discussed the landing page launch yesterday.",
            )

        assert ranked
        assert ranked[0].title == "Launch landing page"


@pytest.mark.asyncio
async def test_recent_life_area_insight_triggers_for_business_pattern():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "lifearea@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        user_id = uuid.UUID(verify.json()["user_id"])

        from app.db import async_session

        async with async_session() as db:
            for idx in range(4):
                await create_memory(
                    db,
                    user_id,
                    type="fact",
                    life_area="business",
                    title=f"Business note {idx}",
                    content=f"Business note {idx} about the product launch and customers.",
                )
            await create_memory(
                db,
                user_id,
                type="fact",
                life_area="health",
                title="Health note",
                content="I went for a walk and slept early.",
            )

            insight = await recent_life_area_insight(db, user_id)

        assert insight is not None
        assert insight["life_area"] == "business"
        assert "business recently" in insight["text"].lower()


@pytest.mark.asyncio
async def test_goal_reflection_linking_detail_views():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "linking@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        goal_res = await client.post(
            "/api/v2/goals",
            headers=headers,
            json={
                "title": "Launch landing page",
                "description": "Ship the first version of the product site.",
                "life_area": "business",
                "status": "active",
                "priority": "high",
            },
        )
        assert goal_res.status_code == 200
        goal_id = goal_res.json()["id"]

        task_res = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={
                "title": "Draft headline",
                "notes": "Make it concise.",
                "goal_id": goal_id,
                "source": "text",
            },
        )
        assert task_res.status_code == 201

        reflection_res = await client.post(
            "/api/v2/reflections",
            headers=headers,
            json={
                "type": "daily",
                "wins": "Made progress",
                "challenges": "Tight timeline",
                "lessons": "Focus on one page",
                "mood": "motivated",
                "goal_id": goal_id,
            },
        )
        assert reflection_res.status_code == 200
        reflection_id = reflection_res.json()["id"]

        goal_detail = await client.get(f"/api/v2/goals/{goal_id}/detail", headers=headers)
        assert goal_detail.status_code == 200
        goal_body = goal_detail.json()
        assert goal_body["goal"]["id"] == goal_id
        assert len(goal_body["linked_tasks"]) == 1
        assert goal_body["linked_tasks"][0]["goal_id"] == goal_id
        assert len(goal_body["linked_reflections"]) == 1
        assert goal_body["linked_reflections"][0]["goal_id"] == goal_id

        reflection_detail = await client.get(
            f"/api/v2/reflections/{reflection_id}/detail",
            headers=headers,
        )
        assert reflection_detail.status_code == 200
        reflection_body = reflection_detail.json()
        assert reflection_body["reflection"]["id"] == reflection_id
        assert reflection_body["linked_goal"]["id"] == goal_id

        filtered_tasks = await client.get(
            "/api/v2/tasks",
            headers=headers,
            params={"goal_id": goal_id},
        )
        assert filtered_tasks.status_code == 200
        assert len(filtered_tasks.json()) == 1

        task_detail = await client.get(
            f"/api/v2/tasks/{task_res.json()['id']}/detail",
            headers=headers,
        )
        assert task_detail.status_code == 200
        task_body = task_detail.json()
        assert task_body["linked_goal"]["id"] == goal_id


@pytest.mark.asyncio
async def test_daily_and_weekly_reflections_save():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "reflectionsave@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        daily = await client.post(
            "/api/v2/reflections/daily",
            headers=headers,
            json={
                "wins": "Finished a task",
                "challenges": "Got distracted",
                "lessons": "Start earlier",
                "mood": "focused",
            },
        )
        assert daily.status_code == 200
        assert daily.json()["id"]

        weekly = await client.post(
            "/api/v2/reflections/weekly",
            headers=headers,
            json={
                "wins": "Stayed consistent",
                "challenges": "Late nights",
                "lessons": "Protect sleep",
                "mood": "reflective",
            },
        )
        assert weekly.status_code == 200
        assert weekly.json()["id"]

        reflection_list = await client.get("/api/v2/reflections", headers=headers)
        assert reflection_list.status_code == 200
        types = {item["type"] for item in reflection_list.json()}
        assert {"daily", "weekly"}.issubset(types)


@pytest.mark.asyncio
async def test_companion_turn_without_planning_does_not_create_task():
    transport = ASGITransport(app=app)
    with (
        patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
        patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
    ):
        mock_llm.return_value = "That sounds tough. Let's take it one step at a time."
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "nodraft@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

            from app.db import async_session

            async with async_session() as db:
                result = await db.execute(select(Task).where(Task.user_id == uuid.UUID(verify.json()["user_id"])))
                before = len(result.scalars().all())

            turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I'm tired today.", "source": "text"},
            )
            assert turn.status_code == 200
            body = turn.json()
            assert body["mode"] in {"companion", "coach"}
            assert body["plan_draft"] is None

            async with async_session() as db:
                result = await db.execute(select(Task).where(Task.user_id == uuid.UUID(verify.json()["user_id"])))
                after = len(result.scalars().all())

            assert before == after
