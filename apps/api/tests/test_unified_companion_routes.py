from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient

from app.auth import create_access_token
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


def _generate_payload(reply: str = "I hear you. Let's stay with what matters."):
    return {
        "reply": reply,
        "mode": "companion",
        "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
        "suggested_actions": [],
        "should_create_task": False,
        "memory_suggestions": [],
        "context_items_used": [],
    }


@pytest.mark.asyncio
async def test_companion_turn_uses_generate_companion_response_and_cleans_reply():
    client, headers, _user_id = await _authed_client("companion-unified@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = _generate_payload(
                '{"reply":"I am with you on this.","mode":"companion","emotion":{"emotion":"neutral"}}'
            )
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Hey AiPal"},
            )

        assert response.status_code == 200
        assert response.json()["reply"] == "I am with you on this."
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_text_turn_prompt_filters_memories_and_caps_context():
    client, headers, user_id = await _authed_client("memory-policy-route@example.com")
    now = datetime.now(UTC)
    async with async_session() as db:
        for index in range(14):
            await create_memory(
                db,
                user_id,
                type="project",
                life_area="business",
                title=f"Qring approved memory {index}",
                content="Qring sales estate customer context.",
                importance=9,
                confidence=0.95,
                approval_status="approved",
                user_approved=True,
            )
        await create_memory(
            db,
            user_id,
            type="project",
            life_area="business",
            title="Qring pending memory",
            content="Pending memory should never be injected.",
            importance=10,
            confidence=0.95,
            approval_status="pending",
            user_approved=False,
        )
        await create_memory(
            db,
            user_id,
            type="project",
            life_area="business",
            title="Qring rejected memory",
            content="Rejected memory should never be injected.",
            importance=10,
            confidence=0.95,
            approval_status="rejected",
            user_approved=False,
        )
        await create_memory(
            db,
            user_id,
            type="project",
            life_area="business",
            title="Qring expired memory",
            content="Expired memory should never be injected.",
            importance=10,
            confidence=0.95,
            approval_status="approved",
            user_approved=True,
            memory_scope="temporary",
            expires_at=now - timedelta(days=1),
        )

    try:
        with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Plain reply."
            response = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "What should I do about Qring sales?"},
            )

        assert response.status_code == 200
        messages = mock_llm.call_args.args[0]
        user_prompt = messages[1]["content"]
        context_lines = [line for line in user_prompt.splitlines() if line.startswith("- memory:")]
        assert "Relevant approved memory:" in user_prompt
        assert len(context_lines) <= 10
        assert "Pending memory should never be injected" not in user_prompt
        assert "Rejected memory should never be injected" not in user_prompt
        assert "Expired memory should never be injected" not in user_prompt
    finally:
        await client.aclose()


def _make_user(user_id: uuid.UUID):
    user = MagicMock()
    user.id = user_id
    user.email = "ws-unified@example.com"
    user.display_name = "Test User"
    user.wake_name = "friend"
    user.about_me = ""
    user.timezone = "UTC"
    return user


@contextmanager
def _no_tts_stream():
    async def _fake_tts_stream(_text, voice=None):
        if False:
            yield b"", "audio/mpeg"

    with patch("app.routers.ws_session.synthesize_stream", side_effect=_fake_tts_stream):
        yield


def test_websocket_text_turn_uses_generate_companion_response():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-unified@example.com")
    user = _make_user(user_id)

    with (
        patch("app.routers.ws_session._user_from_token", new_callable=AsyncMock, return_value=user),
        patch("app.routers.ws_session._rate_limiter") as mock_rl,
        patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate,
        _no_tts_stream(),
    ):
        mock_rl.allow.return_value = True

        mock_generate.return_value = _generate_payload("Hmm, I am with you.")
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                json.loads(ws.receive_text())  # session_started
                ws.send_text(json.dumps({"type": "text_turn", "text": "Hey", "turn_id": "turn-1"}))
                completed = None
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg.get("type") == "turn_complete":
                        completed = msg
                        break
                assert completed is not None
                assert completed["reply"] == "Hmm, I am with you."
                ws.send_text(json.dumps({"type": "end"}))

    assert mock_generate.called
