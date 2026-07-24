from __future__ import annotations

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session
from app.main import app
from app.models import FocusSession, Reflection, TodayItem
from app.services.today_item_service import create_today_item


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_focus_session_lifecycle_updates_today_item_and_creates_reflection_prompt():
    client, headers, user_id = await _authed("focus-lifecycle@example.com")
    try:
        async with async_session() as db:
            item = await create_today_item(
                db,
                user_id,
                type="focus",
                title="Qring deep work",
                source="manual",
                create_notifications=False,
            )

        started = await client.post(f"/api/v2/focus/today-items/{item.id}/start", headers=headers)
        assert started.status_code == 201
        session_id = started.json()["id"]
        assert started.json()["status"] == "active"

        paused = await client.post(f"/api/v2/focus/sessions/{session_id}/pause", headers=headers)
        assert paused.status_code == 200
        assert paused.json()["status"] == "paused"

        resumed = await client.post(f"/api/v2/focus/sessions/{session_id}/resume", headers=headers)
        assert resumed.status_code == 200
        assert resumed.json()["status"] == "active"

        ended = await client.post(
            f"/api/v2/focus/sessions/{session_id}/end",
            headers=headers,
            json={"notes": "Stayed focused after muting notifications."},
        )
        assert ended.status_code == 200
        assert ended.json()["status"] == "completed"
        assert ended.json()["reflection_prompt"]

        async with async_session() as db:
            today_item = await db.get(TodayItem, item.id)
            assert today_item is not None
            assert today_item.status == "completed"
            assert (today_item.metadata_json or {}).get("duration_seconds") is not None
            reflections = (await db.execute(select(Reflection).where(Reflection.user_id == user_id, Reflection.type == "focus"))).scalars().all()
            assert len(reflections) == 1
            assert "Qring deep work" in (reflections[0].summary or "")
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_focus_session_cross_user_access_blocked():
    owner, owner_headers, owner_id = await _authed("focus-owner@example.com")
    other, other_headers, _ = await _authed("focus-other@example.com")
    try:
        async with async_session() as db:
            item = await create_today_item(db, owner_id, type="focus", title="Private focus", source="manual", create_notifications=False)
        started = await owner.post(f"/api/v2/focus/today-items/{item.id}/start", headers=owner_headers)
        assert started.status_code == 201
        session_id = started.json()["id"]

        blocked = await other.post(f"/api/v2/focus/sessions/{session_id}/end", headers=other_headers)
        assert blocked.status_code == 404

        async with async_session() as db:
            sessions = (await db.execute(select(FocusSession).where(FocusSession.user_id == owner_id))).scalars().all()
            assert len(sessions) == 1
            assert sessions[0].status == "active"
    finally:
        await owner.aclose()
        await other.aclose()
