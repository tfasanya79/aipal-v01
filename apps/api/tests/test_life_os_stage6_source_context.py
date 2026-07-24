from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


pytestmark = pytest.mark.asyncio


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, uuid.UUID(verify.json()["user_id"])


async def test_today_source_context_moves_selected_item():
    client, headers, _ = await _authed("stage6-today@example.com")
    try:
        item = await client.post("/api/v2/today-items", headers=headers, json={"type": "task", "title": "Call chairman"})
        response = await client.post(
            "/api/v2/companion/turn",
            headers=headers,
            json={
                "message": "move this to tomorrow",
                "source_context": {"screen": "today", "selected_item_id": item.json()["id"]},
            },
        )
        assert response.status_code == 200
        assert "tomorrow" in response.json()["reply"].lower()
    finally:
        await client.aclose()


async def test_meeting_source_context_summarizes_selected_meeting():
    client, headers, _ = await _authed("stage6-meeting@example.com")
    try:
        meeting = await client.post(
            "/api/v2/meetings",
            headers=headers,
            json={"title": "Recap meeting", "start_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        await client.post(
            f"/api/v2/meetings/{meeting.json()['id']}/notes",
            headers=headers,
            json={"content": "We decided to send the proposal. Follow up tomorrow."},
        )
        response = await client.post(
            "/api/v2/companion/turn",
            headers=headers,
            json={
                "message": "summarize this",
                "source_context": {"screen": "meeting", "selected_meeting_id": meeting.json()["id"]},
            },
        )
        assert response.status_code == 200
        assert "proposal" in response.json()["reply"].lower()
    finally:
        await client.aclose()


async def test_project_source_context_returns_project_risks_and_blocks_cross_user_context():
    owner, owner_headers, _ = await _authed("stage6-project-owner@example.com")
    other, other_headers, _ = await _authed("stage6-project-other@example.com")
    try:
        project = await owner.post(
            "/api/v2/project-rooms",
            headers=owner_headers,
            json={"name": "Qring"},
        )
        project_id = project.json()["id"]
        await owner.patch(
            f"/api/v2/project-rooms/{project_id}",
            headers=owner_headers,
            json={"risks": ["demo conversion"]},
        )
        response = await owner.post(
            "/api/v2/companion/turn",
            headers=owner_headers,
            json={
                "message": "what are the risks?",
                "source_context": {"screen": "project_room", "selected_project_id": project_id},
            },
        )
        assert response.status_code == 200
        assert "demo conversion" in response.json()["reply"].lower()

        blocked = await other.post(
            "/api/v2/companion/turn",
            headers=other_headers,
            json={
                "message": "what are the risks?",
                "source_context": {"screen": "project_room", "selected_project_id": project_id},
            },
        )
        assert blocked.status_code == 200
        assert "demo conversion" not in blocked.json()["reply"].lower()
    finally:
        await owner.aclose()
        await other.aclose()
