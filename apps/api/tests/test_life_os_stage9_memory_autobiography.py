from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Memory


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_memory_autobiography_groups_by_year_and_highlights_milestones():
    client, headers, user_id = await _authed("autobiography@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Memory(
                        user_id=user_id,
                        type="milestone",
                        life_area="business",
                        title="Started AiPal",
                        content="AiPal became a serious project.",
                        event_date=datetime(2026, 1, 12, tzinfo=UTC),
                        importance=5,
                        user_approved=True,
                        approval_status="approved",
                    ),
                    Memory(
                        user_id=user_id,
                        type="win",
                        life_area="business",
                        title="First Estate Customer",
                        content="Closed the first estate customer.",
                        event_date=datetime(2026, 3, 4, tzinfo=UTC),
                        importance=4,
                        user_approved=True,
                        approval_status="approved",
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/memory/autobiography", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_items"] == 2
        assert data["years"][0]["year"] == 2026
        assert data["years"][0]["months"]
        assert [item["title"] for item in data["milestones"]] == ["First Estate Customer", "Started AiPal"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_memory_autobiography_excludes_pending_rejected_and_cross_user_memories():
    client, headers, user_id = await _authed("autobiography-filter@example.com")
    other, _, other_user_id = await _authed("autobiography-filter-other@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Memory(
                        user_id=user_id,
                        type="decision",
                        title="Approved decision",
                        content="This should appear.",
                        user_approved=True,
                        approval_status="approved",
                    ),
                    Memory(
                        user_id=user_id,
                        type="decision",
                        title="Pending decision",
                        content="This should not appear.",
                        user_approved=False,
                        approval_status="pending",
                    ),
                    Memory(
                        user_id=user_id,
                        type="decision",
                        title="Rejected decision",
                        content="This should not appear.",
                        user_approved=False,
                        approval_status="rejected",
                    ),
                    Memory(
                        user_id=other_user_id,
                        type="decision",
                        title="Other user decision",
                        content="This should not appear.",
                        user_approved=True,
                        approval_status="approved",
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/memory/autobiography", headers=headers)
        assert response.status_code == 200
        titles = [item["title"] for year in response.json()["years"] for month in year["months"] for item in month["items"]]
        assert titles == ["Approved decision"]
    finally:
        await client.aclose()
        await other.aclose()
