from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


@pytest.mark.asyncio
async def test_companion_preferences_and_proactive_prompt():
    client, headers, _ = await _authed_client("phase45-pref@example.com")
    try:
        prefs = await client.get("/api/v2/proactive/companion/preferences", headers=headers)
        assert prefs.status_code == 200
        update = await client.patch(
            "/api/v2/proactive/companion/preferences",
            headers=headers,
            json={"tone": "calm", "proactive_enabled": True, "response_length": "balanced"},
        )
        assert update.status_code == 200
        prompt = await client.post("/api/v2/proactive/prompts/generate", headers=headers, json={"force": True})
        assert prompt.status_code == 200
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_understanding_dashboard_and_business_routes():
    client, headers, _ = await _authed_client("phase45-business@example.com")
    try:
        project = await client.post(
            "/api/v2/business/projects",
            headers=headers,
            json={"name": "Qring", "description": "Estate sales project"},
        )
        assert project.status_code == 200
        project_id = project.json()["id"]

        dashboard = await client.get("/api/v2/life-dashboard", headers=headers)
        assert dashboard.status_code == 200
        understanding = await client.get("/api/v2/understanding/profile", headers=headers)
        assert understanding.status_code == 200
        story = await client.get("/api/v2/life-story/accomplishments", headers=headers)
        assert story.status_code == 200
        events = await client.get(f"/api/v2/business/projects/{project_id}/events", headers=headers)
        assert events.status_code == 200
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_connected_sources_and_privacy_routes():
    client, headers, _ = await _authed_client("phase45-connectors@example.com")
    try:
        account = await client.post(
            "/api/v2/connectors/accounts",
            headers=headers,
            json={"provider": "email", "account_label": "Work inbox", "scopes": ["read"], "status": "active"},
        )
        assert account.status_code == 200
        item = await client.post(
            "/api/v2/connectors/items/import",
            headers=headers,
            json={
                "connected_account_id": account.json()["id"],
                "provider": "email",
                "item_type": "email",
                "external_id": "msg-1",
                "title": "Demo tomorrow",
                "content_summary": "Qring demo tomorrow",
            },
        )
        assert item.status_code == 200
        summary = await client.get("/api/v2/connectors/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["accounts"] == 1
    finally:
        await client.aclose()
