from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import NotificationPreference
from app.services.today_item_service import create_today_item


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_today_summary_includes_items_and_creates_notifications_once():
    client, headers, user_id = await _authed("today-summary@example.com")
    now = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    try:
        async with async_session() as db:
            await create_today_item(
                db,
                user_id,
                type="meeting",
                title="Meeting with Stephen",
                start_time=now + timedelta(hours=2),
                due_at=now + timedelta(hours=2),
                source="manual",
            )
            await create_today_item(
                db,
                user_id,
                type="task",
                title="Continue Qring proposal",
                due_at=now + timedelta(hours=1),
                source="manual",
            )

        summary = await client.get("/api/v2/today/summary", headers=headers)
        assert summary.status_code == 200
        assert "Continue Qring proposal" in summary.json()["body"]
        assert "Meeting with Stephen" in summary.json()["body"]

        first = await client.post("/api/v2/today/summary/send", headers=headers)
        second = await client.post("/api/v2/today/summary/send", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert len(first.json()["notifications"]) == 2
        assert second.json()["notifications"] == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_today_summary_email_disabled_prevents_email_notification():
    client, headers, user_id = await _authed("today-summary-disabled@example.com")
    try:
        async with async_session() as db:
            db.add(NotificationPreference(user_id=user_id, in_app_enabled=True, email_enabled=False, push_enabled=False))
            await db.commit()
        response = await client.post("/api/v2/today/summary/send", headers=headers)
        assert response.status_code == 200
        channels = {row["channel"] for row in response.json()["notifications"]}
        assert channels == {"in_app"}
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_next_item_helper_selects_closest_and_respects_quiet_hours():
    client, headers, user_id = await _authed("next-helper@example.com")
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    quiet_start = (now.hour + 2) % 24
    quiet_end = (quiet_start + 1) % 24
    try:
        async with async_session() as db:
            db.add(
                NotificationPreference(
                    user_id=user_id,
                    quiet_hours_start=f"{quiet_start:02d}:00",
                    quiet_hours_end=f"{quiet_end:02d}:00",
                )
            )
            await db.commit()
            await create_today_item(
                db,
                user_id,
                type="task",
                title="Later task",
                due_at=now + timedelta(hours=3),
                source="manual",
            )
            await create_today_item(
                db,
                user_id,
                type="reminder",
                title="Call Estate Chairman",
                due_at=now + timedelta(hours=1),
                start_time=now + timedelta(hours=1),
                source="manual",
            )

        next_item = await client.get("/api/v2/today/next", headers=headers)
        assert next_item.status_code == 200
        assert next_item.json()["item"]["title"] == "Call Estate Chairman"

        notify = await client.post("/api/v2/today/next/notify", headers=headers)
        assert notify.status_code == 200
        assert len(notify.json()["notifications"]) == 2

        duplicate = await client.post("/api/v2/today/next/notify", headers=headers)
        assert duplicate.status_code == 200
        assert duplicate.json()["notifications"] == []
    finally:
        await client.aclose()
