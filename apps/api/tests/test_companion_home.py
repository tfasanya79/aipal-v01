from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Task, TodayItem


pytestmark = pytest.mark.anyio


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, UUID(verify.json()["user_id"])


async def test_companion_home_loads_for_new_user():
    client, headers, _ = await _authed("companion-home-new@example.com")
    try:
        response = await client.get("/api/v2/companion/home", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["message"]
        assert len(data["cards"]) == 6
        assert data["context"]["today_count"] == 0
    finally:
        await client.aclose()


async def test_companion_home_loads_with_today_items_and_next_item():
    client, headers, user_id = await _authed("companion-home-items@example.com")
    try:
        today_morning = datetime.combine(date.today(), time(hour=10, minute=30))
        async with async_session() as db:
            item = TodayItem(
                user_id=user_id,
                type="meeting",
                title="Meeting with Stephen",
                start_time=today_morning,
                status="scheduled",
                source="manual",
            )
            db.add(item)
            await db.commit()

        response = await client.get("/api/v2/companion/home", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["context"]["today_count"] == 1
        assert data["context"]["next_item"]["title"] == "Meeting with Stephen"
    finally:
        await client.aclose()


async def test_companion_home_dynamic_greeting_uses_brain_path():
    client, headers, user_id = await _authed("companion-home-brain@example.com")
    try:
        async with async_session() as db:
            db.add(
                TodayItem(
                    user_id=user_id,
                    type="meeting",
                    title="Qring presentation",
                    start_time=datetime.now(UTC) + timedelta(hours=3),
                    status="scheduled",
                    source="manual",
                )
            )
            await db.commit()

        mock_brief = AsyncMock(
            return_value={
                "message": "Good morning. Your Qring presentation is coming up, if you want to prepare together.",
                "source": "brain",
            }
        )
        with patch("app.services.companion_home_service.generate_today_briefing", mock_brief):
            response = await client.get("/api/v2/companion/home", headers=headers)

        assert response.status_code == 200
        assert mock_brief.await_count == 1
        data = response.json()
        assert data["source"] == "brain"
        assert "Qring presentation" in data["message"]
    finally:
        await client.aclose()


async def test_emotional_companion_message_does_not_create_today_item():
    client, headers, user_id = await _authed("companion-home-emotion@example.com")
    try:
        response = await client.post(
            "/api/v2/companion/turn",
            headers=headers,
            json={"message": "I feel tired today.", "source": "text"},
        )
        assert response.status_code == 200
        async with async_session() as db:
            from sqlalchemy import select

            items = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id))
            tasks = await db.execute(select(Task).where(Task.user_id == user_id))
            assert items.scalars().all() == []
            assert tasks.scalars().all() == []
    finally:
        await client.aclose()
