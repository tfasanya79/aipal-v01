from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session
from app.main import app
from app.models import Goal, Habit, Memory, Task
from app.services.coaching_service import detect_coaching_opportunity
from app.services.mode_router import classify_mode
from app.services.habit_service import detect_habit_signal


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_decision_coaching_and_frameworks():
    client, headers, user_id = await _authed_client("coach@example.com")
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Qring growth", life_area="business", status="active", priority="high")
            db.add(goal)
            await db.commit()
            await db.refresh(goal)
            db.add(
                Memory(
                    user_id=user_id,
                    type="win",
                    life_area="business",
                    title="Qring traction",
                    content="User mentioned traction on Qring.",
                    importance=8,
                    confidence=0.9,
                    user_approved=True,
                    paused=False,
                )
            )
            await db.commit()

        response = await client.post(
            "/api/v2/coaching/decision",
            headers=headers,
            json={
                "question": "Should I focus on Qring or CampusCart?",
                "options": ["Qring", "CampusCart"],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["framework"] == "decision_matrix"
        assert body["recommendation"]
        assert body["analysis"]["matrix"][0]["option"] in {"Qring", "CampusCart"}
        assert {item["option"] for item in body["analysis"]["matrix"]} == {"Qring", "CampusCart"}

        list_response = await client.get("/api/v2/coaching/decisions", headers=headers)
        assert list_response.status_code == 200
        decisions = list_response.json()
        assert len(decisions) == 1

        decision_id = body["decision_id"]
        detail_response = await client.get(f"/api/v2/coaching/decisions/{decision_id}", headers=headers)
        assert detail_response.status_code == 200

        other_client, other_headers, _ = await _authed_client("coach-other@example.com")
        try:
            other_detail = await other_client.get(f"/api/v2/coaching/decisions/{decision_id}", headers=other_headers)
            assert other_detail.status_code == 404
        finally:
            await other_client.aclose()

        framework_response = await client.post(
            "/api/v2/coaching/framework",
            headers=headers,
            json={"framework": "swot", "prompt": "Analyze Qring estate launch"},
        )
        assert framework_response.status_code == 200
        framework_body = framework_response.json()
        assert framework_body["framework"] == "swot"
        assert "strengths" in framework_body["output"]

        frameworks = await client.get("/api/v2/coaching/frameworks", headers=headers)
        assert frameworks.status_code == 200
        assert len(frameworks.json()["frameworks"]) >= 5
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_growth_plans_crud_and_scope():
    client, headers, user_id = await _authed_client("growth@example.com")
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Estate customers", life_area="business", status="active", priority="high")
            db.add(goal)
            await db.commit()
            await db.refresh(goal)

        response = await client.post(
            "/api/v2/growth-plans",
            headers=headers,
            json={"goal_id": str(goal.id), "horizon": "90_day"},
        )
        assert response.status_code == 200
        plan = response.json()
        assert plan["horizon"] == "90_day"
        assert plan["goal_id"] == str(goal.id)
        assert plan["summary"]

        list_response = await client.get("/api/v2/growth-plans", headers=headers)
        assert list_response.status_code == 200
        assert len(list_response.json()) == 1

        detail_response = await client.get(f"/api/v2/growth-plans/{plan['id']}", headers=headers)
        assert detail_response.status_code == 200

        update_response = await client.patch(
            f"/api/v2/growth-plans/{plan['id']}",
            headers=headers,
            json={"status": "paused"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["status"] == "paused"

        other_client, other_headers, _ = await _authed_client("growth-other@example.com")
        try:
            other_detail = await other_client.get(f"/api/v2/growth-plans/{plan['id']}", headers=other_headers)
            assert other_detail.status_code == 404
        finally:
            await other_client.aclose()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_accountability_snapshot_and_compare():
    client, headers, user_id = await _authed_client("accountability@example.com")
    try:
        now = datetime.now(UTC)
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Estate customers", life_area="business", status="active", priority="high")
            db.add(goal)
            db.add(
                Task(
                    user_id=user_id,
                    title="Call estate lead",
                    status="planned",
                    source="text",
                    category="business",
                    due_at=now - timedelta(days=1),
                    created_at=now - timedelta(days=2),
                    updated_at=now - timedelta(days=1),
                )
            )
            db.add(
                Task(
                    user_id=user_id,
                    title="Done task",
                    status="done",
                    source="text",
                    category="business",
                    due_at=now - timedelta(days=4),
                    created_at=now - timedelta(days=5),
                    updated_at=now - timedelta(days=4),
                    completed_at=now - timedelta(days=4),
                )
            )
            db.add(
                Habit(
                    user_id=user_id,
                    name="prayer",
                    life_area="spiritual",
                    frequency="daily",
                    target_count=1,
                    status="active",
                )
            )
            await db.commit()
            habit = (await db.execute(select(Habit).where(Habit.user_id == user_id))).scalar_one()

        snapshot = await client.post(
            "/api/v2/accountability/snapshot",
            headers=headers,
            json={
                "period_start": (now - timedelta(days=6)).date().isoformat(),
                "period_end": now.date().isoformat(),
            },
        )
        assert snapshot.status_code == 200
        snapshot_body = snapshot.json()
        assert snapshot_body["score"] is not None
        assert snapshot_body["reflection"]

        compare = await client.post(
            "/api/v2/accountability/compare",
            headers=headers,
            json={
                "previous_period_start": (now - timedelta(days=13)).date().isoformat(),
                "previous_period_end": (now - timedelta(days=7)).date().isoformat(),
                "current_period_start": (now - timedelta(days=6)).date().isoformat(),
                "current_period_end": now.date().isoformat(),
            },
        )
        assert compare.status_code == 200
        compare_body = compare.json()
        assert compare_body["accountability_question"]
        assert compare_body["current"]["blockers"]

        latest = await client.get("/api/v2/accountability/latest", headers=headers)
        assert latest.status_code == 200
        assert latest.json()["id"] == snapshot_body["id"]

        other_client, other_headers, _ = await _authed_client("accountability-other@example.com")
        try:
            other_snapshot = await other_client.get("/api/v2/accountability/latest", headers=other_headers)
            assert other_snapshot.status_code == 200
            assert other_snapshot.json()["message"]
        finally:
            await other_client.aclose()
        assert habit.id
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_habit_creation_logging_and_detection():
    client, headers, user_id = await _authed_client("habits@example.com")
    try:
        create_response = await client.post(
            "/api/v2/habits",
            headers=headers,
            json={
                "name": "Prayer",
                "life_area": "spiritual",
                "frequency": "daily",
                "target_count": 1,
            },
        )
        assert create_response.status_code == 200
        habit = create_response.json()

        log_response = await client.post(
            f"/api/v2/habits/{habit['id']}/log",
            headers=headers,
            json={"value": 1, "source": "manual", "note": "Morning prayer"},
        )
        assert log_response.status_code == 200

        summary = await client.get("/api/v2/habits/summary", headers=headers)
        assert summary.status_code == 200
        summary_body = summary.json()
        assert len(summary_body["habits"]) == 1

        signal = detect_habit_signal("I prayed every morning this week", "I prayed every morning yesterday too")
        assert signal is not None
        assert signal["life_area"] == "spiritual"

        no_signal = detect_habit_signal("I went to the gym today")
        assert no_signal is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ambiguous_prompt_does_not_force_coach_mode():
    assert detect_coaching_opportunity("I have a plan for today") is None
    assert detect_coaching_opportunity("We need strategy for the trip") is None
    assert classify_mode("We need strategy for the trip", "neutral") == "companion"


@pytest.mark.asyncio
async def test_companion_routes_to_coach_mode_and_suggests_plan_or_habit():
    client, headers, user_id = await _authed_client("coach-turn@example.com")
    try:
        with (
            patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm,
            patch("app.services.companion_orchestrator.plan_extractor.needs_plan_extraction", return_value=False),
        ):
            mock_llm.return_value = "Let's think it through."
            turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Should I focus on Qring or CampusCart?", "source": "text"},
            )
            assert turn.status_code == 200
            body = turn.json()
            assert body["mode"] == "coach"
            assert any(action["type"] == "review_decision" for action in body["suggested_actions"])

            growth_turn = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I want to get 10 estate customers in 90 days.", "source": "text"},
            )
            assert growth_turn.status_code == 200
            growth_body = growth_turn.json()
            assert growth_body["mode"] in {"planner", "coach"}
            assert any(action["type"] == "create_growth_plan" for action in growth_body["suggested_actions"])
    finally:
        await client.aclose()
