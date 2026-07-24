from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _authed(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    return client, {"Authorization": f"Bearer {verify.json()['access_token']}"}


def _payload(reply: str = "Here is the clear, human version."):
    return {
        "reply": reply,
        "mode": "companion",
        "emotion": {"emotion": "neutral", "intensity": 1, "context": "briefing"},
        "suggested_actions": [],
        "should_create_task": False,
        "memory_suggestions": [],
        "context_items_used": [],
    }


@pytest.mark.asyncio
async def test_brain_briefing_today_uses_companion_response_service():
    client, headers = await _authed("brain-today@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _payload("Today looks focused around Qring.")
            response = await client.post("/api/v2/brain/briefing/today", headers=headers, json={})

        assert response.status_code == 200
        assert response.json()["message"] == "Today looks focused around Qring."
        assert response.json()["source"] == "brain"
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_crud_task_list_does_not_call_companion_response_service():
    client, headers = await _authed("brain-crud@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            response = await client.get("/api/v2/tasks", headers=headers)

        assert response.status_code == 200
        mock_generate.assert_not_awaited()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_daily_dynamic_greeting_uses_brain_but_keeps_response_shape():
    client, headers = await _authed("brain-daily@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _payload("Good morning. Start with the one thing that matters.")
            response = await client.get("/api/v2/daily/morning-payload", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["prompt"] == "Good morning. Start with the one thing that matters."
        assert body["source"] == "brain"
        assert "greeting" in body
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_task_nudge_uses_brain_and_missing_task_stays_deterministic():
    client, headers = await _authed("brain-nudge@example.com")
    try:
        due_at = (datetime.now(UTC) + timedelta(minutes=20)).isoformat()
        created = await client.post(
            "/api/v2/tasks",
            headers=headers,
            json={"title": "Call five estate chairmen", "due_at": due_at, "source": "manual"},
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _payload("A gentle nudge: estate calls are coming up soon.")
            response = await client.get(f"/api/v2/daily/task-nudge?task_id={task_id}&minutes=10", headers=headers)

        assert response.status_code == 200
        assert response.json()["text"] == "A gentle nudge: estate calls are coming up soon."
        mock_generate.assert_awaited_once()

        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            missing = await client.get("/api/v2/daily/task-nudge?task_id=999999&minutes=10", headers=headers)

        assert missing.status_code == 200
        assert "nothing coming up" in missing.json()["text"]
        mock_generate.assert_not_awaited()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_connector_sync_deterministic_but_connector_briefing_uses_brain():
    client, headers = await _authed("brain-connector@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            sync = await client.post(
                "/api/v2/connectors/accounts",
                headers=headers,
                json={"provider": "email", "account_label": "Work", "scopes": ["read"], "status": "active"},
            )

        assert sync.status_code == 200
        mock_generate.assert_not_awaited()
        account_id = sync.json()["id"]
        imported = await client.post(
            "/api/v2/connectors/items/import",
            headers=headers,
            json={
                "connected_account_id": account_id,
                "provider": "email",
                "item_type": "email",
                "external_id": "mail-1",
                "title": "Investor follow-up",
                "content_summary": "Follow up with the investor tomorrow.",
            },
        )
        assert imported.status_code == 200

        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _payload("Your important email is the investor follow-up.")
            briefing = await client.post(
                "/api/v2/brain/briefing/connectors",
                headers=headers,
                json={"provider": "email", "source_type": "email"},
            )

        assert briefing.status_code == 200
        assert briefing.json()["message"] == "Your important email is the investor follow-up."
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_proactive_prompt_stores_structured_trigger_and_wording_uses_brain():
    client, headers = await _authed("brain-proactive@example.com")
    try:
        await client.post(
            "/api/v2/memory",
            headers=headers,
            json={
                "type": "important_event",
                "title": "Qring demo",
                "content": "User has a Qring demo tomorrow.",
                "importance": 8,
                "user_approved": True,
                "approval_status": "approved",
            },
        )
        generated = await client.post("/api/v2/proactive/prompts/generate", headers=headers, json={"force": True})
        assert generated.status_code == 200
        body = generated.json()
        assert body["prompt"] == "Structured proactive trigger ready."
        assert body["trigger_metadata"]["trigger_type"]
        assert body["trigger_metadata"]["suggested_intent"] == "gentle_check_in"

        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _payload("How did the Qring demo go?")
            wording = await client.post(
                f"/api/v2/proactive/prompts/{body['id']}/wording",
                headers=headers,
            )

        assert wording.status_code == 200
        assert wording.json()["message"] == "How did the Qring demo go?"
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()
