from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import ProjectRoom, ProjectRoomLink
from sqlalchemy import select


pytestmark = pytest.mark.asyncio


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, uuid.UUID(verify.json()["user_id"])


async def test_create_qring_room_and_summary_auto_links_task_memory_meeting():
    client, headers, user_id = await _authed("stage5-qring@example.com")
    try:
        room = await client.post("/api/v2/project-rooms", headers=headers, json={"name": "Qring", "description": "Estate access project"})
        assert room.status_code == 201
        room_id = room.json()["id"]

        task = await client.post("/api/v2/tasks", headers=headers, json={"title": "Prepare Qring demo", "source": "manual"})
        assert task.status_code == 201
        memory = await client.post(
            "/api/v2/memory",
            headers=headers,
            json={"title": "Qring first customer", "content": "Qring has a promising estate lead.", "type": "project", "approval_status": "approved"},
        )
        assert memory.status_code == 200
        meeting = await client.post(
            "/api/v2/meetings",
            headers=headers,
            json={"title": "Qring estate demo", "start_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        assert meeting.status_code == 201

        summary = await client.get(f"/api/v2/project-rooms/{room_id}/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["room"]["name"] == "Qring"
        assert summary.json()["room"]["business_project_id"] is None
        assert summary.json()["tasks"]
        assert summary.json()["memories"]
        assert summary.json()["meetings"]
        assert isinstance(summary.json()["progress"], int)
        async with async_session() as db:
            rooms = (await db.execute(select(ProjectRoom).where(ProjectRoom.user_id == user_id))).scalars().all()
            assert len(rooms) == 1
            assert rooms[0].name == "Qring"
    finally:
        await client.aclose()


async def test_project_room_manual_link_and_cross_user_access_blocked():
    owner, owner_headers, _ = await _authed("stage5-owner@example.com")
    other, other_headers, _ = await _authed("stage5-other@example.com")
    try:
        room = await owner.post("/api/v2/project-rooms", headers=owner_headers, json={"name": "CampusCart"})
        room_id = room.json()["id"]
        link = await owner.post(
            f"/api/v2/project-rooms/{room_id}/link",
            headers=owner_headers,
            json={"linked_type": "idea", "linked_id": "idea-1"},
        )
        assert link.status_code == 200
        async with async_session() as db:
            links = (await db.execute(select(ProjectRoomLink).where(ProjectRoomLink.linked_id == "idea-1"))).scalars().all()
            assert len(links) == 1

        blocked = await other.get(f"/api/v2/project-rooms/{room_id}", headers=other_headers)
        assert blocked.status_code == 404
    finally:
        await owner.aclose()
        await other.aclose()
