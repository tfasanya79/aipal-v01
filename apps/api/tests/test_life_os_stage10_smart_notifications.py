from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session
from app.main import app
from app.models import Commitment, Meeting, NotificationPreference
from app.services.today_item_service import create_today_item


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_smart_meeting_notification_uses_meeting_context_and_prevents_duplicates():
    client, headers, user_id = await _authed("smart-meeting@example.com")
    try:
        async with async_session() as db:
            meeting = Meeting(
                user_id=user_id,
                title="Stephen payment review",
                start_time=datetime.now(UTC) + timedelta(minutes=45),
                participants=["Stephen"],
                notes="Discuss Sammya EMS payment and outstanding balance.",
            )
            db.add(meeting)
            await db.commit()
            await db.refresh(meeting)

        first = await client.post(f"/api/v2/notifications/smart/meeting/{meeting.id}", headers=headers)
        second = await client.post(f"/api/v2/notifications/smart/meeting/{meeting.id}", headers=headers)
        assert first.status_code == 200
        assert len(first.json()["notifications"]) == 2
        assert second.json()["notifications"] == []
        row = first.json()["notifications"][0]
        assert row["type"] == "smart_meeting_prep"
        assert row["metadata"]["meeting_id"] == str(meeting.id)
        assert row["body"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_smart_commitment_progress_counts_completed_and_remaining():
    client, headers, user_id = await _authed("smart-commitments@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Commitment(user_id=user_id, title="Call five chairmen", content="Call five estate chairmen", status="completed"),
                    Commitment(user_id=user_id, title="Call remaining chairmen", content="Call two remaining estate chairmen", status="open"),
                ]
            )
            await db.commit()

        response = await client.post("/api/v2/notifications/smart/commitments", headers=headers, json={"keyword": "chairmen"})
        assert response.status_code == 200
        rows = response.json()["notifications"]
        assert len(rows) == 2
        assert rows[0]["type"] == "smart_commitment_progress"
        assert rows[0]["metadata"]["completed"] == 1
        assert rows[0]["metadata"]["remaining"] == 1

        listed = await client.get("/api/v2/notifications", headers=headers)
        assert any(row["type"] == "smart_commitment_progress" for row in listed.json())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_smart_missed_followup_is_gentle_and_quiet_hours_respected():
    client, headers, user_id = await _authed("smart-missed@example.com")
    now = datetime.now(UTC)
    try:
        async with async_session() as db:
            item = await create_today_item(
                db,
                user_id,
                type="task",
                title="Finish pitch deck",
                status="missed",
                source="manual",
                create_notifications=False,
            )
            quiet_start = now.strftime("%H:%M")
            quiet_end = (now + timedelta(hours=1)).strftime("%H:%M")
            db.add(NotificationPreference(user_id=user_id, quiet_hours_start=quiet_start, quiet_hours_end=quiet_end))
            await db.commit()

        blocked = await client.post(f"/api/v2/notifications/smart/missed/{item.id}", headers=headers)
        assert blocked.status_code == 200
        assert blocked.json()["notifications"] == []

        async with async_session() as db:
            pref = (await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))).scalar_one_or_none()
            if pref:
                pref.quiet_hours_start = None
                pref.quiet_hours_end = None
                await db.commit()
        created = await client.post(f"/api/v2/notifications/smart/missed/{item.id}", headers=headers)
        assert created.status_code == 200
        assert len(created.json()["notifications"]) == 2
        assert "shame" not in created.json()["notifications"][0]["body"].lower()
    finally:
        await client.aclose()
