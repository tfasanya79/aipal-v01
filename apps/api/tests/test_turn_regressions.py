from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import async_session
from app.main import app
from app.models import ProactivePrompt
from app.services.proactive_conversation_service import _prompt_count_today


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers, verify.json()["user_id"]


@pytest.mark.asyncio
async def test_turn_sessions_alias_matches_flutter_route():
    client, headers, _ = await _authed_client("turn-sessions-alias@example.com")
    try:
        response = await client.get("/api/v2/turn/sessions", headers=headers)
        assert response.status_code == 200
        assert response.json() == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_prompt_count_today_uses_datetime_range_not_date_string():
    client, _headers, user_id = await _authed_client("prompt-count-range@example.com")
    await client.aclose()
    user_uuid = UUID(user_id)

    now = datetime.now(UTC)
    async with async_session() as db:
        db.add(
            ProactivePrompt(
                user_id=user_uuid,
                trigger_type="test",
                prompt="Today prompt",
                status="delivered",
                delivered_at=now,
            )
        )
        db.add(
            ProactivePrompt(
                user_id=user_uuid,
                trigger_type="test",
                prompt="Old prompt",
                status="delivered",
                delivered_at=now - timedelta(days=2),
            )
        )
        await db.commit()

        assert await _prompt_count_today(db, user_uuid) == 1


@pytest.mark.asyncio
async def test_audio_turn_returns_graceful_response_when_orchestrator_fails():
    client, headers, _ = await _authed_client("audio-graceful-failure@example.com")
    try:
        with (
            patch("app.routers.turn.transcribe_path", return_value="hello there"),
            patch("app.routers.turn.run_conversation", new_callable=AsyncMock) as run_turn,
        ):
            run_turn.side_effect = RuntimeError("simulated companion failure")
            response = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.webm", b"not-real-audio-but-transcribed", "audio/webm")},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["transcript"] == "hello there"
        assert "trouble thinking through" in body["reply"]
    finally:
        await client.aclose()
