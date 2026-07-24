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


async def test_weekly_planner_creates_draft_without_today_items_until_confirmed():
    client, headers, _ = await _authed("stage3-weekly@example.com")
    try:
        before = await client.get("/api/v2/today-items/range", headers=headers, params={
            "start_date": datetime.now(UTC).date().isoformat(),
            "end_date": (datetime.now(UTC).date() + timedelta(days=7)).isoformat(),
        })
        assert before.json() == []

        today = datetime.now(UTC).date()
        draft = await client.post("/api/v2/planner/weekly", headers=headers, json={"week_start": today.isoformat()})
        assert draft.status_code == 200
        assert draft.json()["requires_confirmation"] is True
        assert len(draft.json()["proposed_tasks"]) == 5

        still_empty = await client.get("/api/v2/today-items/range", headers=headers, params={
            "start_date": datetime.now(UTC).date().isoformat(),
            "end_date": (datetime.now(UTC).date() + timedelta(days=7)).isoformat(),
        })
        assert still_empty.json() == []

        confirmed = await client.post("/api/v2/planner/current/confirm", headers=headers)
        assert confirmed.status_code == 200
        assert len(confirmed.json()["created"]) >= 5

        after = await client.get("/api/v2/today-items/range", headers=headers, params={
            "start_date": datetime.now(UTC).date().isoformat(),
            "end_date": (datetime.now(UTC).date() + timedelta(days=7)).isoformat(),
        })
        assert len(after.json()) >= 5
    finally:
        await client.aclose()


async def test_daily_planner_respects_existing_meeting_hour_and_includes_breaklike_review():
    client, headers, _ = await _authed("stage3-daily@example.com")
    try:
        target = datetime.now(UTC).date()
        meeting_time = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        meeting = await client.post(
            "/api/v2/today-items",
            headers=headers,
            json={"type": "meeting", "title": "Existing meeting", "start_time": meeting_time.isoformat()},
        )
        assert meeting.status_code == 201

        draft = await client.post("/api/v2/planner/daily", headers=headers, json={"date": target.isoformat()})
        assert draft.status_code == 200
        tasks = draft.json()["proposed_tasks"]
        hours = [datetime.fromisoformat(item["due_at"]).hour for item in tasks]
        assert hours.count(10) == 0
        assert any("review" in item["title"].lower() for item in tasks)
    finally:
        await client.aclose()


async def test_life_roadmap_and_90_day_plans_are_drafts():
    client, headers, _ = await _authed("stage3-roadmap@example.com")
    try:
        ninety = await client.post("/api/v2/planner/90-day", headers=headers, json={})
        assert ninety.status_code == 200
        assert ninety.json()["intent"] == "90_day_plan"
        assert ninety.json()["requires_confirmation"] is True

        life = await client.post("/api/v2/planner/life-roadmap", headers=headers)
        assert life.status_code == 200
        assert life.json()["intent"] == "life_roadmap"
        assert life.json()["requires_confirmation"] is True
    finally:
        await client.aclose()
