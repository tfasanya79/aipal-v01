from __future__ import annotations

from datetime import UTC, datetime, timedelta
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import async_session
from app.main import app
from app.models import Task
from app.services.commitment_service import create_commitment, extract_commitments, list_due_followups


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, uuid.UUID(verify.json()["user_id"])


async def _task_count(user_id: uuid.UUID) -> int:
    async with async_session() as db:
        result = await db.execute(select(Task).where(Task.user_id == user_id))
        return len(result.scalars().all())


@pytest.mark.asyncio
async def test_commitment_extraction_detects_common_phrases_without_creating_tasks():
    client, headers, user_id = await _authed_client("commitment-extract@example.com")
    try:
        async with async_session() as db:
            chairmen = await extract_commitments(
                db,
                user_id,
                "I will call 5 estate chairmen tomorrow.",
            )
            stephen = await extract_commitments(
                db,
                user_id,
                "I promised Stephen I'd send the invoice.",
            )
            low_confidence = await extract_commitments(
                db,
                user_id,
                "I will maybe follow up with the investor if I can.",
            )

        assert chairmen and chairmen[0]["requires_confirmation"] is False
        assert "estate chairmen" in chairmen[0]["title"].lower()
        assert stephen and stephen[0]["requires_confirmation"] is False
        assert "Stephen" in stephen[0]["content"]
        assert low_confidence and low_confidence[0]["requires_confirmation"] is True

        assert await _task_count(user_id) == 0
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_ambiguous_need_to_requires_time_anchor_and_relative_dates_are_parsed():
    client, headers, user_id = await _authed_client("commitment-ambiguity@example.com")
    try:
        async with async_session() as db:
            vague = await extract_commitments(
                db,
                user_id,
                "I need to get better at sales.",
            )
            tomorrow = await extract_commitments(
                db,
                user_id,
                "I need to call Stephen tomorrow morning.",
            )
            in_days = await extract_commitments(
                db,
                user_id,
                "I plan to send the report in 3 days.",
            )
            weekday = await extract_commitments(
                db,
                user_id,
                "I will follow up with the investor next Monday afternoon.",
            )

        assert vague == []
        assert tomorrow and tomorrow[0]["requires_confirmation"] is False
        assert tomorrow[0]["due_at"] is not None
        assert tomorrow[0]["due_at"].hour == 9
        assert in_days and in_days[0]["due_at"] is not None
        assert in_days[0]["due_at"] > datetime.now(UTC) + timedelta(days=2)
        assert weekday and weekday[0]["due_at"] is not None
        assert weekday[0]["due_at"].weekday() == 0
        assert weekday[0]["due_at"].hour == 14
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_due_followup_complete_and_dismiss_hide_commitments():
    client, headers, user_id = await _authed_client("commitment-due@example.com")
    try:
        async with async_session() as db:
            due = await create_commitment(
                db,
                user_id,
                "Call 5 estate chairmen",
                "I will call 5 estate chairmen tomorrow.",
                due_at=datetime.now(UTC) - timedelta(days=1),
                follow_up_at=datetime.now(UTC) - timedelta(hours=1),
                confidence=0.9,
            )
            dismissible = await create_commitment(
                db,
                user_id,
                "Send Stephen invoice",
                "I promised Stephen I'd send the invoice.",
                follow_up_at=datetime.now(UTC) - timedelta(hours=1),
                confidence=0.86,
            )

        due_response = await client.get("/api/v2/commitments/due", headers=headers)
        assert due_response.status_code == 200
        assert {item["id"] for item in due_response.json()} >= {str(due.id), str(dismissible.id)}

        completed = await client.post(f"/api/v2/commitments/{due.id}/complete", headers=headers)
        assert completed.status_code == 200
        dismissed = await client.post(f"/api/v2/commitments/{dismissible.id}/dismiss", headers=headers)
        assert dismissed.status_code == 200

        due_after = await client.get("/api/v2/commitments/due", headers=headers)
        assert all(item["id"] not in {str(due.id), str(dismissible.id)} for item in due_after.json())
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_commitment_api_create_list_update_and_cross_user_scope():
    client_a, headers_a, _ = await _authed_client("commitment-api-owner@example.com")
    client_b, headers_b, _ = await _authed_client("commitment-api-other@example.com")
    try:
        created = await client_a.post(
            "/api/v2/commitments",
            headers=headers_a,
            json={
                "title": "Follow up with investor",
                "content": "I'm going to follow up with the investor next week.",
                "follow_up_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
                "confidence": 0.84,
            },
        )
        assert created.status_code == 200
        commitment_id = created.json()["id"]

        listed = await client_a.get("/api/v2/commitments", headers=headers_a)
        assert listed.status_code == 200
        assert any(item["id"] == commitment_id for item in listed.json())

        updated = await client_a.patch(
            f"/api/v2/commitments/{commitment_id}",
            headers=headers_a,
            json={"title": "Investor follow-up", "confidence": 0.91},
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Investor follow-up"

        blocked = await client_b.post(f"/api/v2/commitments/{commitment_id}/complete", headers=headers_b)
        assert blocked.status_code == 404
    finally:
        await client_a.aclose()
        await client_b.aclose()


@pytest.mark.asyncio
async def test_companion_commitment_statement_creates_commitment_not_task_and_due_context_is_gentle():
    client, headers, user_id = await _authed_client("commitment-companion@example.com")
    try:
        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "That sounds important. I'll remember it as something to follow up on tomorrow."
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I will call 5 estate chairmen tomorrow.", "source": "text"},
            )
        assert response.status_code == 200
        assert response.json()["plan_draft"] is None
        assert await _task_count(user_id) == 0

        commitments = await client.get("/api/v2/commitments", headers=headers)
        assert any("estate chairmen" in item["title"].lower() for item in commitments.json())

        async with async_session() as db:
            await create_commitment(
                db,
                user_id,
                "Call 5 estate chairmen",
                "I will call 5 estate chairmen tomorrow.",
                due_at=datetime.now(UTC) - timedelta(days=1),
                follow_up_at=datetime.now(UTC) - timedelta(minutes=1),
                confidence=0.9,
            )

        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "You planned to call 5 estate chairmen. Did you get a chance to do that?"
            followup_response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Hey", "source": "text"},
            )
            prompt_text = mock_llm.call_args.args[0][1]["content"]

        assert followup_response.status_code == 200
        assert "Did you get a chance" in prompt_text
        assert any(action["type"] == "commitment_follow_up" for action in followup_response.json()["suggested_actions"])
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_commitment_links_to_knowledge_graph_entities_when_available():
    client, headers, user_id = await _authed_client("commitment-graph@example.com")
    try:
        async with async_session() as db:
            qring = await extract_commitments(
                db,
                user_id,
                "I'm going to follow up with Qring estate leads next week.",
            )
            stephen = await extract_commitments(
                db,
                user_id,
                "I promised Stephen I'd send the invoice.",
            )

        assert qring[0]["related_entity_name"] == "Qring"
        assert qring[0]["related_entity_type"] == "project"
        assert stephen[0]["related_entity_name"] == "Stephen"
        assert stephen[0]["related_entity_type"] == "person"

        async with async_session() as db:
            due_rows = await list_due_followups(db, user_id)
            assert isinstance(due_rows, list)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_commitment_entity_linking_avoids_generic_capitalized_words():
    client, headers, user_id = await _authed_client("commitment-graph-safe@example.com")
    try:
        async with async_session() as db:
            generic = await extract_commitments(
                db,
                user_id,
                "I will send the invoice tomorrow.",
            )
            person = await extract_commitments(
                db,
                user_id,
                "I will send Stephen the invoice tomorrow.",
            )

        assert generic and generic[0]["related_entity_name"] is None
        assert person and person[0]["related_entity_name"] == "Stephen"
        assert person[0]["related_entity_type"] == "person"
    finally:
        await client.aclose()
