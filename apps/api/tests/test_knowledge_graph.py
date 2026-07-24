from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import async_session
from app.main import app
from app.models import MemoryEntityLink
from app.services.memory_service import create_memory


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


async def _create_memory(client: AsyncClient, headers: dict[str, str], **payload) -> str:
    response = await client.post("/api/v2/memory", headers=headers, json=payload)
    assert response.status_code == 200
    return response.json()["id"]


async def _search_entities(client: AsyncClient, headers: dict[str, str], query: str, entity_type: str | None = None):
    params = {"query": query}
    if entity_type:
        params["entity_type"] = entity_type
    response = await client.get("/api/v2/knowledge/search", headers=headers, params=params)
    assert response.status_code == 200
    return response.json()


async def _memory_link_count(memory_id: uuid.UUID) -> int:
    async with async_session() as db:
        result = await db.execute(
            select(func.count()).select_from(MemoryEntityLink).where(MemoryEntityLink.memory_id == memory_id)
        )
        return int(result.scalar_one() or 0)


@pytest.mark.asyncio
async def test_qring_entity_created_from_qring_memory():
    client, headers, _ = await _authed_client("knowledge-graph-qring@example.com")
    try:
        await _create_memory(
            client,
            headers,
            type="important_event",
            life_area="business",
            title="Qring demo",
            content="I have a Qring demo tomorrow.",
            approval_status="approved",
            user_approved=True,
            confidence=0.91,
        )

        entities = await _search_entities(client, headers, "Qring", "project")
        assert any(entity["name"] == "Qring" for entity in entities)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_demo_event_and_sales_concern_link_to_qring():
    client, headers, _ = await _authed_client("knowledge-graph-links@example.com")
    try:
        await _create_memory(
            client,
            headers,
            type="important_event",
            life_area="business",
            title="Qring demo",
            content="I have a Qring demo tomorrow.",
            approval_status="approved",
            user_approved=True,
            confidence=0.93,
        )
        await _create_memory(
            client,
            headers,
            type="recurring_concern",
            life_area="business",
            title="Sales concern",
            content="Nobody is buying and I feel stuck.",
            approval_status="approved",
            user_approved=True,
            confidence=0.88,
        )

        qring = next(entity for entity in await _search_entities(client, headers, "Qring", "project") if entity["name"] == "Qring")
        graph = await client.get(f"/api/v2/knowledge/entities/{qring['id']}/graph", headers=headers)
        assert graph.status_code == 200
        payload = graph.json()
        assert any(edge["relation_type"] == "belongs_to" for edge in payload["edges"])
        assert any(edge["relation_type"] == "blocks" for edge in payload["edges"])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_person_entity_created_from_named_people():
    client, headers, _ = await _authed_client("knowledge-graph-people@example.com")
    try:
        await _create_memory(
            client,
            headers,
            type="relationship",
            life_area="relationships",
            title="Stephen conversation",
            content="Stephen and I had a great conversation about the deck.",
            approval_status="approved",
            user_approved=True,
            confidence=0.89,
        )

        entities = await _search_entities(client, headers, "Stephen", "person")
        assert any(entity["name"] == "Stephen" for entity in entities)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_hidden_memories_are_not_linked():
    client, headers, user_id = await _authed_client("knowledge-graph-hidden@example.com")
    try:
        pending_id = await _create_memory(
            client,
            headers,
            type="important_event",
            life_area="business",
            title="Pending demo",
            content="Qring demo next week.",
            approval_status="pending",
            user_approved=False,
            confidence=0.4,
        )
        assert await _memory_link_count(uuid.UUID(pending_id)) == 0

        rejected_id = await _create_memory(
            client,
            headers,
            type="important_event",
            life_area="business",
            title="Rejected demo",
            content="Qring demo next week.",
            approval_status="approved",
            user_approved=True,
            confidence=0.9,
        )
        reject = await client.post(f"/api/v2/memory/{rejected_id}/reject", headers=headers)
        assert reject.status_code == 200
        assert await _memory_link_count(uuid.UUID(rejected_id)) == 0

        async with async_session() as db:
            expired = await create_memory(
                db,
                user_id,
                type="important_event",
                life_area="business",
                title="Expired demo",
                content="Qring demo already happened.",
                memory_scope="temporary",
                expires_at=datetime.now(UTC) - timedelta(days=1),
                approval_status="approved",
            )
            assert await _memory_link_count(expired.id) == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_edited_memory_updates_links():
    client, headers, _ = await _authed_client("knowledge-graph-edit@example.com")
    try:
        memory_id = await _create_memory(
            client,
            headers,
            type="important_event",
            life_area="business",
            title="Qring demo",
            content="I have a Qring demo tomorrow.",
            approval_status="approved",
            user_approved=True,
            confidence=0.93,
        )

        before = await _search_entities(client, headers, "Qring", "project")
        assert any(entity["name"] == "Qring" for entity in before)

        edit = await client.patch(
            f"/api/v2/memory/{memory_id}/edit",
            headers=headers,
            json={
                "title": "CampusCart demo",
                "content": "I have a CampusCart demo next week.",
                "type": "important_event",
                "life_area": "business",
                "approval_status": "approved",
                "user_approved": True,
            },
        )
        assert edit.status_code == 200

        qring_entity = next(entity for entity in await _search_entities(client, headers, "Qring", "project") if entity["name"] == "Qring")
        qring_graph = await client.get(f"/api/v2/knowledge/entities/{qring_entity['id']}/graph", headers=headers)
        assert qring_graph.status_code == 200
        assert all(memory["id"] != memory_id for memory in qring_graph.json()["related_memories"])

        after_campus = await _search_entities(client, headers, "CampusCart", "project")
        assert any(entity["name"] == "CampusCart" for entity in after_campus)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_no_cross_user_graph_access_and_summary_returns_useful_structure():
    client_a, headers_a, _ = await _authed_client("knowledge-graph-owner@example.com")
    client_b, headers_b, _ = await _authed_client("knowledge-graph-other@example.com")
    try:
        _ = await _create_memory(
            client_a,
            headers_a,
            type="important_event",
            life_area="business",
            title="Qring demo",
            content="I have a Qring demo tomorrow.",
            approval_status="approved",
            user_approved=True,
            confidence=0.93,
        )
        entity = next(entity for entity in await _search_entities(client_a, headers_a, "Qring", "project") if entity["name"] == "Qring")

        blocked_entity = await client_b.get(f"/api/v2/knowledge/entities/{entity['id']}", headers=headers_b)
        assert blocked_entity.status_code == 404

        blocked_graph = await client_b.get(f"/api/v2/knowledge/entities/{entity['id']}/graph", headers=headers_b)
        assert blocked_graph.status_code == 404

        summary = await client_a.get("/api/v2/knowledge/summary", headers=headers_a)
        assert summary.status_code == 200
        payload = summary.json()
        assert "counts" in payload
        assert "top_entities" in payload
        assert "patterns" in payload
        assert payload["counts"]["entities"] >= 1
    finally:
        await client_a.aclose()
        await client_b.aclose()
