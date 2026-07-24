from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.services.memory_service import create_memory


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


async def _search(client: AsyncClient, headers: dict[str, str], query: str) -> list[dict]:
    response = await client.post("/api/v2/memory/search", headers=headers, json={"query": query, "limit": 20})
    assert response.status_code == 200
    return response.json()


@pytest.mark.asyncio
async def test_pending_memory_does_not_appear_in_normal_retrieval_and_approves_cleanly():
    client, headers, _ = await _authed_client("memory-confidence-pending@example.com")
    try:
        created = await client.post(
            "/api/v2/memory",
            headers=headers,
            json={
                "type": "important_event",
                "life_area": "business",
                "title": "Qring demo",
                "content": "Preparing for the Qring demo next week.",
                "confidence": 0.62,
                "approval_status": "pending",
                "user_approved": False,
                "suggested_reason": "Needs confirmation",
            },
        )
        assert created.status_code == 200
        memory_id = created.json()["id"]

        pending = await client.get("/api/v2/memory/pending", headers=headers)
        assert pending.status_code == 200
        assert any(item["id"] == memory_id for item in pending.json())

        search_before = await _search(client, headers, "Qring demo")
        assert all(item["id"] != memory_id for item in search_before)

        approved = await client.post(f"/api/v2/memory/{memory_id}/approve", headers=headers)
        assert approved.status_code == 200

        search_after = await _search(client, headers, "Qring demo")
        assert any(item["id"] == memory_id for item in search_after)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_rejected_memory_does_not_appear_in_retrieval():
    client, headers, _ = await _authed_client("memory-confidence-rejected@example.com")
    try:
        created = await client.post(
            "/api/v2/memory",
            headers=headers,
            json={
                "type": "win",
                "life_area": "business",
                "title": "Closed first customer",
                "content": "Closed first estate customer.",
            },
        )
        assert created.status_code == 200
        memory_id = created.json()["id"]

        rejected = await client.post(f"/api/v2/memory/{memory_id}/reject", headers=headers)
        assert rejected.status_code == 200
        assert all(item["id"] != memory_id for item in await _search(client, headers, "customer"))
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_temporary_memory_expires_and_editing_updates_safely():
    client, headers, user_id = await _authed_client("memory-confidence-temp@example.com")
    try:
        expired_id: uuid.UUID
        async with async_session() as db:
            expired = await create_memory(
                db,
                user_id,
                type="important_event",
                life_area="business",
                title="Expired demo",
                content="A demo that already expired.",
                memory_scope="temporary",
                expires_at=datetime.now(UTC) - timedelta(days=1),
                approval_status="approved",
            )
            expired_id = expired.id

        search_expired = await _search(client, headers, "expired demo")
        assert all(item["id"] != str(expired_id) for item in search_expired)

        created = await client.post(
            "/api/v2/memory",
            headers=headers,
            json={
                "type": "important_event",
                "life_area": "business",
                "title": "Qring demo",
                "content": "Preparing for the Qring demo next week.",
                "confidence": 0.61,
                "approval_status": "pending",
                "user_approved": False,
            },
        )
        memory_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v2/memory/{memory_id}/edit",
            headers=headers,
            json={
                "title": "Qring demo prep",
                "content": "Preparing for the Qring demo next Friday.",
                "life_area": "business",
                "type": "important_event",
                "memory_scope": "temporary",
                "expires_at": (datetime.now(UTC) + timedelta(days=2)).isoformat(),
                "suggested_reason": "Updated by user before approval",
            },
        )
        assert edited.status_code == 200

        pending = await client.get("/api/v2/memory/pending", headers=headers)
        assert any(item["id"] == memory_id and item["title"] == "Qring demo prep" for item in pending.json())

        approved = await client.post(f"/api/v2/memory/{memory_id}/approve", headers=headers)
        assert approved.status_code == 200

        search_after = await _search(client, headers, "Qring demo prep")
        assert any(item["id"] == memory_id and item["title"] == "Qring demo prep" for item in search_after)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cross_user_memory_approval_is_blocked():
    client_a, headers_a, _ = await _authed_client("memory-confidence-owner@example.com")
    client_b, headers_b, _ = await _authed_client("memory-confidence-other@example.com")
    try:
        created = await client_a.post(
            "/api/v2/memory",
            headers=headers_a,
            json={
                "type": "important_event",
                "life_area": "business",
                "title": "Owner memory",
                "content": "Owner pending memory.",
                "approval_status": "pending",
                "user_approved": False,
            },
        )
        memory_id = created.json()["id"]

        blocked = await client_b.post(f"/api/v2/memory/{memory_id}/approve", headers=headers_b)
        assert blocked.status_code == 404
    finally:
        await client_a.aclose()
        await client_b.aclose()
