from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Goal, KnowledgeEntity, Meeting, Memory, Task
from app.services.today_item_service import create_today_item


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_weekly_and_monthly_insights_handle_sparse_user_without_fake_data():
    client, headers, _ = await _authed("insights-sparse@example.com")
    try:
        weekly = await client.get("/api/v2/insights/weekly", headers=headers)
        monthly = await client.get("/api/v2/insights/monthly", headers=headers)
        assert weekly.status_code == 200
        assert monthly.status_code == 200
        assert weekly.json()["sparse"] is True
        assert monthly.json()["sparse"] is True
        assert weekly.json()["narrative"]["source"] == "brain"
        assert monthly.json()["narrative"]["source"] == "brain"
        assert weekly.json()["narrative"]["message"]
        assert weekly.json()["summary"]["tasks"] == 0
        assert weekly.json()["growth"]["wins"] == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_weekly_insights_reference_real_tasks_meetings_memories_and_people_only():
    client, headers, user_id = await _authed("insights-rich@example.com")
    now = datetime.now(UTC)
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Close Qring pilot", life_area="business", status="active")
            db.add(goal)
            await db.flush()
            db.add_all(
                [
                    Task(
                        user_id=user_id,
                        title="Prepare Qring proposal",
                        status="done",
                        category="business",
                        goal_id=goal.id,
                    ),
                    Meeting(
                        user_id=user_id,
                        title="Stephen planning call",
                        start_time=now + timedelta(hours=2),
                        status="scheduled",
                    ),
                    Memory(
                        user_id=user_id,
                        type="win",
                        life_area="business",
                        title="Estate demo improved",
                        content="The estate demo improved this week.",
                        sentiment="positive",
                        user_approved=True,
                        approval_status="approved",
                    ),
                    Memory(
                        user_id=user_id,
                        type="win",
                        life_area="business",
                        title="Rejected hidden signal",
                        content="This should not appear.",
                        sentiment="positive",
                        user_approved=False,
                        approval_status="rejected",
                    ),
                    KnowledgeEntity(user_id=user_id, entity_type="person", name="Stephen", confidence=0.9),
                ]
            )
            await create_today_item(
                db,
                user_id,
                type="focus",
                title="Qring focus block",
                status="completed",
                source="manual",
                goal_id=goal.id,
                metadata={"duration_minutes": 45},
            )

        response = await client.get("/api/v2/insights/weekly", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["sparse"] is False
        assert data["summary"]["tasks"] == 1
        assert data["summary"]["completed_tasks"] == 1
        assert data["summary"]["meetings"] == 1
        assert data["summary"]["focus_minutes"] == 45
        assert "Estate demo improved" in data["growth"]["wins"]
        assert "Rejected hidden signal" not in data["growth"]["wins"]
        assert data["relationships"]["people"][0]["name"] == "Stephen"
        assert data["goals"][0]["title"] == "Close Qring pilot"
        assert data["narrative"]["source"] == "brain"
        assert data["narrative"]["message"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_deep_life_area_insights_returns_ranked_real_areas():
    client, headers, user_id = await _authed("insights-life-area@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Goal(user_id=user_id, title="Learn sales", life_area="learning", status="active"),
                    Memory(
                        user_id=user_id,
                        type="lesson",
                        life_area="learning",
                        title="Sales script improved",
                        content="The new script helped.",
                        user_approved=True,
                        approval_status="approved",
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/insights/life-areas/deep", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["sparse"] is False
        assert data["top_areas"][0]["life_area"] == "learning"
        assert data["narrative"]["source"] == "brain"
        assert data["narrative"]["message"]
    finally:
        await client.aclose()
