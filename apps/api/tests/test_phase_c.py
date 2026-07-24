from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.timezone_util import user_local_today

_NOW = datetime(2026, 6, 11, 10, 0, tzinfo=timezone.utc)


def test_user_local_today_invalid_tz_falls_back_utc():
    day = user_local_today("Not/A_Real_Zone")
    assert day.year >= 2020


@pytest.mark.asyncio
async def test_live_greeting_in_live_no_push_to_talk():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "live@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        with patch("app.routers.daily.conv_svc.has_chatted_today", new_callable=AsyncMock) as chatted:
            chatted.return_value = True
            r = await client.get("/api/v2/daily/live-greeting?in_live=true", headers=headers)
            assert r.status_code == 200
            text = r.json()["text"].lower()
            assert "tap to talk" not in text
            assert "press to talk" not in text
            assert "hold to talk" not in text
            assert "listening" in text


@pytest.mark.asyncio
async def test_live_greeting_wake_intro_when_requested():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "wake@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        r = await client.get(
            "/api/v2/daily/live-greeting?in_live=true&wake_enabled=true&show_wake_intro=true",
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert "hi pal" in body["text"].lower()
        assert body.get("wake_word_hint") is not None
        assert "on screen" not in body["wake_word_hint"].lower()
        text = body["text"].lower()
        assert "tap to talk" not in text
        assert "press to talk" not in text
        assert "hold to talk" not in text


@pytest.mark.asyncio
async def test_daily_routes_fallback_when_brain_briefing_fails():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "daily-fallback@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        with patch("app.routers.daily.generate_today_briefing", new_callable=AsyncMock) as briefing:
            briefing.side_effect = RuntimeError("provider offline")
            checkin = await client.get("/api/v2/daily/checkin-payload", headers=headers)
            greeting = await client.get("/api/v2/daily/live-greeting?in_live=true", headers=headers)

        assert checkin.status_code == 200
        assert greeting.status_code == 200
        assert checkin.json()["prompt"]
        assert greeting.json()["text"]


@pytest.mark.asyncio
async def test_text_turn_includes_today_snapshot():
    with (
        patch("app.services.companion_orchestrator.generate_companion_response", new_callable=AsyncMock) as mock_generate,
        patch("app.services.companion_orchestrator.plan_extractor.extract_plan", new_callable=AsyncMock) as mock_extract,
        patch("app.services.companion_orchestrator.list_active_goals", new_callable=AsyncMock) as mock_goals,
        patch("app.services.companion_orchestrator.task_svc.list_tasks", new_callable=AsyncMock) as mock_tasks,
    ):

        mock_generate.return_value = {
            "reply": "Sure.",
            "mode": "assistant",
            "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
            "suggested_actions": [],
            "should_create_task": False,
            "memory_suggestions": [],
            "context_items_used": [],
        }
        mock_extract.return_value = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}
        mock_goals.return_value = [
            SimpleNamespace(
                id=1,
                title="Health",
                description=None,
                life_area="health",
                status="active",
                priority=1,
                target_date=None,
                created_at=_NOW,
                updated_at=_NOW,
            )
        ]
        mock_tasks.return_value = [
            SimpleNamespace(
                id=2,
                title="Swim",
                notes=None,
                due_at=None,
                priority=1,
                status="planned",
                source="text",
                parent_task_id=None,
                estimated_minutes=None,
                sort_order=0,
                category=None,
                created_at=_NOW,
                updated_at=_NOW,
                completed_at=None,
                subtasks=[],
            )
        ]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            reg = await client.post("/api/v2/auth/register", json={"email": "snap@example.com"})
            verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
            headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "what's next?"},
            )
            assert r.status_code == 200
            task_context = mock_generate.await_args.kwargs["tasks"]
            assert any(task["title"] == "Swim" for task in task_context)
