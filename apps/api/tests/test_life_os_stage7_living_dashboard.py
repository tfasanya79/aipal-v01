from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Goal, Habit, HabitLog, KnowledgeEntity, Memory
from app.services.today_item_service import create_today_item


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_living_dashboard_loads_for_new_user_without_fake_data():
    client, headers, _ = await _authed("living-dashboard-new@example.com")
    try:
        response = await client.get("/api/v2/life-dashboard/living", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["today"]["total"] == 0
        assert data["today"]["completion_percent"] == 0
        assert data["next_up"] is None
        assert data["goals"] == []
        assert data["relationships"] == []
        assert data["insights"] == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_living_dashboard_uses_real_today_goal_habit_relationship_and_mood_data():
    client, headers, user_id = await _authed("living-dashboard-rich@example.com")
    today_at_2 = datetime.combine(date.today(), time(hour=14, minute=0))
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Close first Qring customer", life_area="business", status="active")
            habit = Habit(user_id=user_id, name="Reading", life_area="learning", status="active")
            db.add_all(
                [
                    goal,
                    habit,
                    KnowledgeEntity(user_id=user_id, entity_type="person", name="Stephen", confidence=0.9),
                    Memory(
                        user_id=user_id,
                        type="win",
                        title="Estate demo went well",
                        content="The estate demo felt stronger than last time.",
                        sentiment="positive",
                        user_approved=True,
                        approval_status="approved",
                    ),
                ]
            )
            await db.flush()
            db.add(HabitLog(user_id=user_id, habit_id=habit.id, logged_at=datetime.now(UTC), value=1))
            await create_today_item(
                db,
                user_id,
                type="meeting",
                title="Estate Demo",
                start_time=today_at_2,
                due_at=today_at_2,
                status="scheduled",
                goal_id=goal.id,
                source="manual",
            )
            await create_today_item(
                db,
                user_id,
                type="focus",
                title="Qring deep work",
                start_time=today_at_2 + timedelta(hours=1),
                status="completed",
                goal_id=goal.id,
                source="manual",
                metadata={"duration_minutes": 90},
            )

        response = await client.get("/api/v2/life-dashboard/living", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["today"]["total"] == 2
        assert data["today"]["completed"] == 1
        assert data["today"]["completion_percent"] == 50
        assert data["next_up"]["title"] == "Estate Demo"
        assert data["goals"][0]["title"] == "Close first Qring customer"
        assert data["goals"][0]["progress"] == 50
        assert data["focus"]["minutes_today"] == 90
        assert data["mood"]["trend"] == "Improving"
        assert data["relationships"][0]["name"] == "Stephen"
        assert data["habits"][0]["name"] == "Reading"
        assert data["habits"][0]["recent_logs"] == 1
        assert any("Estate Demo" in insight for insight in data["insights"])
    finally:
        await client.aclose()

