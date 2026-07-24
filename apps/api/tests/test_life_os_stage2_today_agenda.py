from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Task


pytestmark = pytest.mark.asyncio


async def _authed(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, uuid.UUID(verify.json()["user_id"])


async def test_today_agenda_groups_tasks_meetings_focus_and_completed():
    client, headers, _ = await _authed("stage2-agenda@example.com")
    try:
        today = datetime.now(UTC).date()
        now = datetime.combine(today, datetime.min.time(), tzinfo=UTC).replace(hour=8)
        task = await client.post(
            "/api/v2/today-items",
            headers=headers,
            json={"type": "task", "title": "Morning task", "due_at": now.replace(hour=9, minute=0).isoformat()},
        )
        meeting = await client.post(
            "/api/v2/today-items",
            headers=headers,
            json={"type": "meeting", "title": "Estate demo", "start_time": (now + timedelta(hours=2)).isoformat()},
        )
        focus = await client.post(
            "/api/v2/today-items",
            headers=headers,
            json={"type": "focus", "title": "Deep work", "start_time": (now + timedelta(hours=3)).isoformat()},
        )
        assert task.status_code == meeting.status_code == focus.status_code == 201
        await client.post(f"/api/v2/today-items/{task.json()['id']}/complete", headers=headers)

        agenda = await client.get("/api/v2/today/agenda", headers=headers, params={"day": today.isoformat()})
        assert agenda.status_code == 200
        sections = agenda.json()["sections"]
        assert sections["completed"][0]["title"] == "Morning task"
        assert sections["meetings"][0]["title"] == "Estate demo"
        assert sections["focus"][0]["title"] == "Deep work"
    finally:
        await client.aclose()


async def test_snooze_and_reschedule_sync_linked_task():
    client, headers, user_id = await _authed("stage2-reschedule@example.com")
    try:
        original = datetime.now(UTC) + timedelta(hours=1)
        created = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={"title": "Linked task", "due_at": original.isoformat(), "source": "manual"},
        )
        task_id = created.json()["id"]
        items = await client.get("/api/v2/today-items", headers=headers)
        item = next(row for row in items.json() if row["task_id"] == task_id)

        snoozed = await client.post(f"/api/v2/today-items/{item['id']}/snooze", headers=headers, json={"minutes": 45})
        assert snoozed.status_code == 200

        new_time = datetime.now(UTC) + timedelta(days=1)
        rescheduled = await client.post(
            f"/api/v2/today-items/{item['id']}/reschedule",
            headers=headers,
            json={"new_time": new_time.isoformat()},
        )
        assert rescheduled.status_code == 200
        async with async_session() as db:
            task = await db.get(Task, task_id)
            assert task is not None
            assert task.user_id == user_id
            assert task.due_at is not None
            task_due = task.due_at.replace(tzinfo=UTC) if task.due_at.tzinfo is None else task.due_at
            assert abs((task_due - new_time).total_seconds()) < 2
    finally:
        await client.aclose()


async def test_start_focus_marks_today_item_without_cross_user_access():
    client_a, headers_a, _ = await _authed("stage2-focus-owner@example.com")
    client_b, headers_b, _ = await _authed("stage2-focus-other@example.com")
    try:
        item = await client_a.post(
            "/api/v2/today-items",
            headers=headers_a,
            json={"type": "focus", "title": "Focus on Qring"},
        )
        item_id = item.json()["id"]
        blocked = await client_b.post(f"/api/v2/today-items/{item_id}/start-focus", headers=headers_b)
        assert blocked.status_code == 404

        started = await client_a.post(f"/api/v2/today-items/{item_id}/start-focus", headers=headers_a)
        assert started.status_code == 200
        assert "focus_started_at" in started.json()["metadata"]
    finally:
        await client_a.aclose()
        await client_b.aclose()
