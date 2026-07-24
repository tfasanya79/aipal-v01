from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


pytestmark = pytest.mark.asyncio


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, uuid.UUID(verify.json()["user_id"])


async def test_create_meeting_appears_in_today_and_upcoming():
    client, headers, _ = await _authed("stage4-meeting@example.com")
    try:
        start = datetime.now(UTC) + timedelta(hours=2)
        meeting = await client.post(
            "/api/v2/meetings",
            headers=headers,
            json={"title": "Meeting with Stephen", "start_time": start.isoformat(), "participants": ["Stephen"]},
        )
        assert meeting.status_code == 201
        meeting_id = meeting.json()["id"]

        today = await client.get("/api/v2/today-items", headers=headers, params={"day": start.date().isoformat()})
        assert any(item["calendar_event_id"] == meeting_id and item["type"] == "meeting" for item in today.json())

        upcoming = await client.get("/api/v2/meetings/upcoming", headers=headers)
        assert any(row["id"] == meeting_id for row in upcoming.json())
    finally:
        await client.aclose()


async def test_meeting_brief_uses_brain_path():
    client, headers, _ = await _authed("stage4-brief@example.com")
    try:
        start = datetime.now(UTC) + timedelta(hours=1)
        meeting = await client.post(
            "/api/v2/meetings",
            headers=headers,
            json={"title": "Sammya payment review", "start_time": start.isoformat(), "participants": ["Stephen"], "notes": "Discuss outstanding balance."},
        )
        mock_brief = AsyncMock(return_value={"message": "Review the outstanding balance and agree the next step."})
        with patch("app.services.meeting_assistant_service.generate_notification_briefing", mock_brief):
            brief = await client.post(f"/api/v2/meetings/{meeting.json()['id']}/brief", headers=headers)
        assert brief.status_code == 200
        assert mock_brief.await_count == 1
        assert "outstanding balance" in brief.json()["brief"]
    finally:
        await client.aclose()


async def test_meeting_notes_summary_action_items_and_followups():
    client, headers, _ = await _authed("stage4-notes@example.com")
    try:
        start = datetime.now(UTC) + timedelta(hours=1)
        meeting = await client.post(
            "/api/v2/meetings",
            headers=headers,
            json={"title": "Estate demo recap", "start_time": start.isoformat()},
        )
        notes = await client.post(
            f"/api/v2/meetings/{meeting.json()['id']}/notes",
            headers=headers,
            json={"content": "We agreed to send the proposal. Follow up with the chairman tomorrow. Confirm pricing."},
        )
        assert notes.status_code == 200
        assert notes.json()["summary"]
        assert len(notes.json()["action_items"]) >= 2

        summary = await client.post(f"/api/v2/meetings/{meeting.json()['id']}/summarize", headers=headers)
        assert summary.status_code == 200
        followups = await client.post(f"/api/v2/meetings/{meeting.json()['id']}/followups", headers=headers)
        assert followups.status_code == 200
        assert followups.json()["followups"]
    finally:
        await client.aclose()


async def test_cross_user_meeting_access_blocked():
    owner, owner_headers, _ = await _authed("stage4-owner@example.com")
    other, other_headers, _ = await _authed("stage4-other@example.com")
    try:
        meeting = await owner.post(
            "/api/v2/meetings",
            headers=owner_headers,
            json={"title": "Private meeting", "start_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        )
        blocked = await other.get(f"/api/v2/meetings/{meeting.json()['id']}", headers=other_headers)
        assert blocked.status_code == 404
    finally:
        await owner.aclose()
        await other.aclose()
