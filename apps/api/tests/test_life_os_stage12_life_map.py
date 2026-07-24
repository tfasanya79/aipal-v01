from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import Goal, Habit, Memory, Reflection, Task


async def _authed_client(email: str = "life-map@example.com"):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    register = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": register.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}, UUID(verify.json()["user_id"])


@pytest.mark.anyio
async def test_life_map_returns_all_areas_for_sparse_user():
    client, headers, _ = await _authed_client("life-map-sparse@example.com")
    try:
        response = await client.get("/api/v2/life-map", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert payload["sparse"] is True
        assert len(payload["areas"]) == 7
        assert {area["life_area"] for area in payload["areas"]} == {
            "business",
            "health",
            "finance",
            "learning",
            "relationships",
            "spiritual",
            "personal_growth",
        }
        assert all(area["progress"] == 0 for area in payload["areas"])
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_life_map_links_real_data_by_area():
    client, headers, user_id = await _authed_client("life-map-rich@example.com")
    try:
        async with async_session() as db:
            goal = Goal(user_id=user_id, title="Close Qring pilot", life_area="business", status="active")
            db.add(goal)
            await db.flush()
            db.add_all(
                [
                    Memory(
                        user_id=user_id,
                        type="achievement",
                        life_area="business",
                        title="Won first estate demo",
                        content="The first estate demo went well.",
                        importance=5,
                        confidence=0.95,
                        approval_status="approved",
                        user_approved=True,
                        paused=False,
                        sentiment="positive",
                    ),
                    Task(
                        user_id=user_id,
                        title="Finish Qring proposal",
                        category="business",
                        goal_id=goal.id,
                        status="planned",
                    ),
                    Habit(user_id=user_id, name="Morning workout", life_area="health", status="active"),
                    Reflection(
                        user_id=user_id,
                        goal_id=goal.id,
                        type="weekly",
                        wins="Demo confidence improved.",
                        summary="Business progress felt stronger this week.",
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/life-map", headers=headers)
        assert response.status_code == 200
        areas = {area["life_area"]: area for area in response.json()["areas"]}
        assert areas["business"]["goal_count"] == 1
        assert areas["business"]["task_count"] == 1
        assert areas["business"]["memory_count"] == 1
        assert areas["business"]["reflection_count"] == 1
        assert areas["business"]["win_count"] == 1
        assert areas["business"]["progress"] > 0
        assert areas["health"]["habit_count"] == 1

        detail = await client.get("/api/v2/life-map/business", headers=headers)
        assert detail.status_code == 200
        body = detail.json()
        assert body["label"] == "Business"
        assert body["goals"][0]["title"] == "Close Qring pilot"
        assert body["tasks"][0]["title"] == "Finish Qring proposal"
        assert body["wins"][0]["title"] == "Won first estate demo"
        assert body["patterns"]
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_life_map_excludes_unapproved_and_cross_user_data():
    client, headers, user_id = await _authed_client("life-map-private@example.com")
    other_client, other_headers, other_user_id = await _authed_client("life-map-private-other@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Memory(
                        user_id=user_id,
                        type="milestone",
                        life_area="learning",
                        title="Approved learning milestone",
                        content="Started a course.",
                        approval_status="approved",
                        user_approved=True,
                        paused=False,
                    ),
                    Memory(
                        user_id=user_id,
                        type="milestone",
                        life_area="learning",
                        title="Pending private memory",
                        content="Should not appear.",
                        approval_status="pending",
                        user_approved=False,
                        paused=False,
                    ),
                    Memory(
                        user_id=user_id,
                        type="milestone",
                        life_area="learning",
                        title="Expired private memory",
                        content="Should not appear.",
                        approval_status="approved",
                        user_approved=True,
                        paused=False,
                        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    ),
                    Goal(user_id=other_user_id, title="Other finance goal", life_area="finance"),
                ]
            )
            await db.commit()

        detail = await client.get("/api/v2/life-map/learning", headers=headers)
        assert detail.status_code == 200
        titles = [memory["title"] for memory in detail.json()["memories"]]
        assert titles == ["Approved learning milestone"]

        other_detail = await other_client.get("/api/v2/life-map/finance", headers=other_headers)
        assert other_detail.status_code == 200
        assert [goal["title"] for goal in other_detail.json()["goals"]] == ["Other finance goal"]
    finally:
        await client.aclose()
        await other_client.aclose()


@pytest.mark.anyio
async def test_life_area_detail_rejects_unknown_area():
    client, headers, _ = await _authed_client("life-map-invalid@example.com")
    try:
        response = await client.get("/api/v2/life-map/unknown", headers=headers)
        assert response.status_code == 404
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_life_map_semantically_links_items_without_explicit_area():
    client, headers, user_id = await _authed_client("life-map-semantic@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Goal(user_id=user_id, title="Close more Qring estate demos", description=None),
                    Task(user_id=user_id, title="Send Qring estate demo proposal", notes=None, status="planned"),
                    Habit(user_id=user_id, name="Prayer and quiet Bible reading", status="active"),
                    Memory(
                        user_id=user_id,
                        type="lesson",
                        title="Finished a learning book",
                        content="Reading and studying a new course helped me practice.",
                        approval_status="approved",
                        user_approved=True,
                        paused=False,
                    ),
                    Reflection(
                        user_id=user_id,
                        type="weekly",
                        summary="I felt more confident during customer meetings and demos.",
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/life-map", headers=headers)
        assert response.status_code == 200
        areas = {area["life_area"]: area for area in response.json()["areas"]}
        assert areas["business"]["goal_count"] >= 1
        assert areas["business"]["task_count"] >= 1
        assert areas["business"]["reflection_count"] >= 1
        assert areas["spiritual"]["habit_count"] == 1
        assert areas["learning"]["memory_count"] == 1
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_life_map_briefing_uses_brain_path(monkeypatch):
    client, headers, _ = await _authed_client("life-map-briefing@example.com")
    calls: list[dict[str, object]] = []

    async def fake_briefing(db, user, *, life_map, life_area=None):
        calls.append({"life_map": life_map, "life_area": life_area})
        return {
            "message": "Your Life Map is starting to take shape.",
            "source": "brain",
            "mode": "companion",
            "emotion": {"emotion": "neutral", "intensity": 1},
        }

    monkeypatch.setattr("app.routers.life_map.generate_life_map_briefing", fake_briefing)
    try:
        response = await client.get("/api/v2/life-map/briefing", headers=headers)
        assert response.status_code == 200
        assert response.json()["source"] == "brain"
        assert response.json()["message"] == "Your Life Map is starting to take shape."
        assert calls
        assert calls[0]["life_area"] is None
        assert "areas" in calls[0]["life_map"]
    finally:
        await client.aclose()


@pytest.mark.anyio
async def test_ambiguous_life_signals_are_suggested_for_review_not_dropped():
    client, headers, user_id = await _authed_client("life-map-ambiguous@example.com")
    try:
        async with async_session() as db:
            db.add_all(
                [
                    Task(user_id=user_id, title="Budget course", notes=None, status="planned"),
                    Memory(
                        user_id=user_id,
                        type="note",
                        title="Budget course note",
                        content="A small note about budget course ideas.",
                        approval_status="approved",
                        user_approved=True,
                        paused=False,
                    ),
                ]
            )
            await db.commit()

        response = await client.get("/api/v2/life-map", headers=headers)
        assert response.status_code == 200
        payload = response.json()
        assert payload["suggested_activity"] >= 2
        areas = {area["life_area"]: area for area in payload["areas"]}
        assert areas["finance"]["suggested_count"] >= 1
        assert areas["learning"]["suggested_count"] >= 1

        finance = await client.get("/api/v2/life-map/finance", headers=headers)
        assert finance.status_code == 200
        suggested = finance.json()["suggested_items"]
        assert suggested
        assert all(item["confidence"] == "needs_review" for item in suggested)
    finally:
        await client.aclose()
