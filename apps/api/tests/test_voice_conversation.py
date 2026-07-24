from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


async def _authed_client(email: str):
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    reg = await client.post("/api/v2/auth/register", json={"email": email})
    verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
    headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}
    return client, headers


@pytest.mark.asyncio
async def test_text_turn_uses_companion_response_service_and_cleans_reply():
    client, headers = await _authed_client("text-unified@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate:
            mock_generate.return_value = {
                "reply": "reply: I hear you. Let's stay with the real thread.\nmode: companion",
                "mode": "companion",
                "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
                "suggested_actions": [],
                "should_create_task": False,
                "memory_suggestions": [],
                "context_items_used": [],
            }
            response = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "I'm thinking about Qring today.", "session_id": "text-session"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["reply"] == "I hear you. Let's stay with the real thread."
        mock_generate.assert_awaited_once()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_tts_voice_endpoint_returns_multiple_real_voice_ids():
    client, headers = await _authed_client("tts-voices@example.com")
    try:
        response = await client.get("/api/v2/turn/tts/voices", headers=headers)
        assert response.status_code == 200
        voices = response.json()
        ids = {voice["id"] for voice in voices}
        assert {"calm_female", "calm_male", "coach", "friendly"}.issubset(ids)
        assert len(voices) >= 8
        assert all(voice["name"] and voice["provider"] for voice in voices)
        profiles = await client.get("/api/v2/voice/profiles", headers=headers)
        assert profiles.status_code == 200
        assert profiles.json()["default"] == "calm_female"
        first_profile = profiles.json()["profiles"][0]
        assert first_profile["profile_id"]
        assert first_profile["display_name"]
        assert "is_distinct_voice_supported" in first_profile
        assert "fallback_note" in first_profile
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_audio_turn_accepts_session_id():
    with (
        patch("app.routers.turn.transcribe_path", return_value="hello there"),
        patch("app.services.companion_orchestrator.generate_companion_response", new_callable=AsyncMock) as mock_generate,
        patch("app.routers.turn.synthesize", new_callable=AsyncMock) as mock_tts,
    ):
        mock_generate.return_value = {
            "reply": "Hi!",
            "mode": "companion",
            "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
            "suggested_actions": [],
            "should_create_task": False,
            "memory_suggestions": [],
            "context_items_used": [],
        }
        mock_tts.return_value = (b"audio", "audio/mpeg")

        client, headers = await _authed_client("audio@example.com")
        try:
            r = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"fake", "audio/mp4")},
                data={"session_id": "sess-123"},
            )
            assert r.status_code == 200
            body = r.json()
            assert body["session_id"]
            assert body["mode"] == "companion"
            assert body["reply"] == "Hi!"
            mock_generate.assert_awaited_once()
        finally:
            await client.aclose()


@pytest.mark.asyncio
async def test_single_word_audio_transcript_uses_the_unified_brain():
    with (
        patch("app.routers.turn.transcribe_path", return_value="Continue"),
        patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
        ) as mock_generate,
        patch("app.routers.turn.synthesize", new_callable=AsyncMock) as mock_tts,
    ):
        mock_generate.return_value = {
            "reply": "Let’s continue from there.",
            "mode": "companion",
            "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
            "suggested_actions": [],
            "should_create_task": False,
            "memory_suggestions": [],
            "context_items_used": [],
        }
        mock_tts.return_value = (b"", None)
        client, headers = await _authed_client("audio-single-word@example.com")
        try:
            response = await client.post(
                "/api/v2/turn/audio",
                headers=headers,
                files={"file": ("turn.m4a", b"fake", "audio/mp4")},
            )
        finally:
            await client.aclose()

    assert response.status_code == 200
    assert response.json()["reply"] == "Let’s continue from there."
    mock_generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_task_creation_does_not_happen_before_companion_reasoning():
    client, headers = await _authed_client("action-last@example.com")
    try:
        with (
            patch(
                "app.services.companion_orchestrator.generate_companion_response",
                new_callable=AsyncMock,
            ) as mock_generate,
            patch("app.services.tasks.create_task", new_callable=AsyncMock) as mock_create_task,
        ):
            mock_generate.return_value = {
                "reply": "That sounds like something we can turn into a task if you want.",
                "mode": "assistant",
                "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
                "suggested_actions": [
                    {
                        "type": "create_task",
                        "label": "Create task",
                        "description": "Call Stephen tomorrow.",
                        "requires_confirmation": True,
                    }
                ],
                "should_create_task": True,
                "memory_suggestions": [],
                "context_items_used": [],
            }
            r = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "Create a task to call Stephen tomorrow."},
            )

        assert r.status_code == 200
        mock_generate.assert_awaited_once()
        mock_create_task.assert_not_called()
        assert r.json()["tool_actions"] == ["Create task"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_greeting_in_live_short_resume_after_chat():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v2/auth/register", json={"email": "resume@example.com"})
        verify = await client.post("/api/v2/auth/verify", json={"token": reg.json()["dev_token"]})
        headers = {"Authorization": f"Bearer {verify.json()['access_token']}"}

        with patch("app.routers.daily.conv_svc.has_chatted_today", new_callable=AsyncMock) as chatted:
            chatted.return_value = True
            r = await client.get("/api/v2/daily/live-greeting?in_live=true", headers=headers)
            assert r.status_code == 200
            text = r.json()["text"].lower()
            assert "listening" in text
            assert "plan waiting" not in text
            assert "next up" not in text


@pytest.mark.asyncio
async def test_needs_plan_extraction_skips_casual_chat():
    from app.services.plan_extractor import needs_plan_extraction

    assert not needs_plan_extraction("how are you feeling today?")
    assert needs_plan_extraction("remind me to swim at 6pm")
    assert needs_plan_extraction("I finished swimming")
