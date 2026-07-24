"""WebSocket integration tests for Live Voice v2."""

import asyncio
import base64
import json
import threading
import uuid
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from app.auth import create_access_token
from app.main import app
from app.services.stt_provider import STTFinal, STTPartial
from app.services.turn_detection import HybridTurnDetector


def _make_user(user_id: uuid.UUID):
    user = MagicMock()
    user.id = user_id
    user.email = "ws-test@example.com"
    return user


@contextmanager
def _mock_ws_db():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.get = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__.return_value = db
    cm.__aexit__.return_value = None
    resumed_state = MagicMock()
    resumed_state.current_topic = None
    resumed_state.current_goal = None
    resumed_state.user_intent = None
    resumed_state.pending_action = None
    with (
        patch("app.routers.ws_session.async_session", return_value=cm),
        patch(
            "app.routers.ws_session.conversation_state_manager.end",
            new_callable=AsyncMock,
        ),
        patch(
            "app.routers.ws_session.conversation_state_manager.resume",
            new_callable=AsyncMock,
            return_value=resumed_state,
        ),
        patch("app.routers.ws_session.mark_user_speaking", new_callable=AsyncMock),
        patch("app.routers.ws_session.mark_ai_speaking", new_callable=AsyncMock),
        patch("app.routers.ws_session.mark_listening", new_callable=AsyncMock),
        patch("app.routers.ws_session.mark_interrupted", new_callable=AsyncMock),
    ):
        yield


async def _fake_voice_stream(*_args, **_kwargs):
    yield {"type": "context_ready", "metrics": {"context_items_count": 1}}
    yield {"type": "reply_delta", "text": "Hi there."}
    yield {"type": "sentence_ready", "text": "Hi there."}
    yield {
        "type": "turn_complete",
        "reply": "Hi there.",
        "tool_actions": [],
        "draft_confirmed": False,
        "metrics": {"llm_ttft_ms": 10},
    }


async def _fake_tts_stream(_text, voice=None):
    yield b"audio-bytes", "audio/mpeg"


def _recv_until(ws, target_type: str, *, max_messages: int = 30):
    for _ in range(max_messages):
        msg = json.loads(ws.receive_text())
        if msg.get("type") == target_type:
            return msg
        if msg.get("type") == "error":
            pytest.fail(msg.get("message"))
    pytest.fail(f"Did not receive {target_type}")


def test_ws_rejects_client_owned_turn_boundaries():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-test@example.com")
    user = _make_user(user_id)

    mock_stt = MagicMock()
    mock_stt.on_speech_start = AsyncMock()
    mock_stt.on_speech_end = AsyncMock(return_value="hello there")
    mock_stt.consume_metrics = MagicMock(return_value={"stt_partial_ms": 42})
    mock_stt.feed_audio = AsyncMock(return_value=None)

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.routers.ws_session.get_streaming_stt", return_value=mock_stt),
        patch("app.routers.ws_session.run_voice_turn_stream", new=_fake_voice_stream),
        patch("app.routers.ws_session.synthesize_stream", side_effect=_fake_tts_stream),
        patch("app.routers.ws_session._rate_limiter") as mock_rl,
    ):
        mock_rl.allow.return_value = True
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                started = json.loads(ws.receive_text())
                assert started["type"] == "session_started"

                turn_id = "turn-1"
                ws.send_text(json.dumps({"type": "speech_start", "turn_id": turn_id}))
                error = _recv_until(ws, "error")
                assert error["code"] == "client_turn_boundary_unsupported"
                assert error["turn_id"] == turn_id
                mock_stt.on_speech_start.assert_not_awaited()
                ws.send_text(json.dumps({"type": "end"}))

    assert uuid.UUID(started["session_id"])


async def _slow_voice_stream(*_args, cancel_event=None, **_kwargs):
    yield {"type": "reply_delta", "text": "Still working..."}
    while cancel_event is None or not cancel_event.is_set():
        await asyncio.sleep(0.02)


def test_ws_interrupt_cancels_turn():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-test@example.com")
    user = _make_user(user_id)

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.routers.ws_session.run_voice_turn_stream", new=_slow_voice_stream),
        patch("app.routers.ws_session.synthesize_stream", side_effect=_fake_tts_stream),
        patch("app.routers.ws_session._rate_limiter") as mock_rl,
    ):
        mock_rl.allow.return_value = True
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                json.loads(ws.receive_text())  # session_started

                turn_id = "turn-interrupt"
                ws.send_text(
                    json.dumps(
                        {
                            "type": "text_turn",
                            "text": "interrupt me",
                            "turn_id": turn_id,
                        }
                    )
                )
                _recv_until(ws, "reply_delta")

                ws.send_text(json.dumps({"type": "interrupt", "turn_id": turn_id}))
                cancelled = _recv_until(ws, "turn_cancelled")
                assert cancelled["turn_id"] == turn_id
                duplicate_cancellations = 0
                ws.send_text(json.dumps({"type": "ping"}))
                for _ in range(10):
                    followup = json.loads(ws.receive_text())
                    if followup.get("type") == "turn_cancelled":
                        duplicate_cancellations += 1
                    if followup.get("type") == "pong":
                        break
                assert duplicate_cancellations == 0
                ws.send_text(json.dumps({"type": "end"}))


def test_ws_legacy_speech_end_cannot_finalize_a_turn():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-audio-contract@example.com")
    user = _make_user(user_id)
    mock_stt = MagicMock()
    mock_stt.on_speech_start = AsyncMock()
    mock_stt.feed_audio = AsyncMock(
        return_value=STTPartial(
            text="hello",
            confidence=0.82,
            language="en",
            language_confidence=0.97,
            audio_ms=40,
            stability=0.5,
        )
    )
    mock_stt.on_speech_end = AsyncMock(return_value=STTFinal(text="", audio_ms=40))
    mock_stt.consume_metrics = MagicMock(return_value={})
    mock_stt.reset = MagicMock()

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.routers.ws_session.get_streaming_stt", return_value=mock_stt),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                started = json.loads(ws.receive_text())
                assert started["voice_protocol"] == "4.0"
                assert started["turn_detection"]["authority"] == "server"
                turn_id = "legacy-turn"
                ws.send_text(json.dumps({"type": "speech_end", "turn_id": turn_id}))
                error = _recv_until(ws, "error")
                assert error["code"] == "client_turn_boundary_unsupported"
                assert error["turn_id"] == turn_id
                mock_stt.on_speech_end.assert_not_awaited()
                ws.send_text(json.dumps({"type": "end"}))


def test_ws_server_neural_detector_owns_speech_start_and_endpoint():
    class ProbabilitySequence:
        name = "test_neural_vad"

        def __init__(self):
            self.values = [0.9, 0.9] + [0.05] * 12

        def score(self, _pcm):
            return self.values.pop(0) if self.values else 0.05

    detector = HybridTurnDetector(speech_provider=ProbabilitySequence())
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-phase4@example.com")
    user = _make_user(user_id)
    mock_stt = MagicMock()
    mock_stt.on_speech_start = AsyncMock()
    mock_stt.feed_audio = AsyncMock(
        return_value=STTPartial(
            text="I have finished explaining the whole request now.",
            confidence=0.92,
            language="en",
            stability=0.95,
            audio_ms=400,
        )
    )
    mock_stt.on_speech_end = AsyncMock(return_value=STTFinal(text="", audio_ms=560))
    mock_stt.consume_metrics = MagicMock(return_value={})
    mock_stt.reset = MagicMock()

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.routers.ws_session.HybridTurnDetector", return_value=detector),
        patch("app.routers.ws_session.get_streaming_stt", return_value=mock_stt),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                started = json.loads(ws.receive_text())
                assert started["turn_detection"]["authority"] == "server"
                assert (
                    started["turn_detection"]["semantic_provider"]
                    == "multilingual_semantic_local"
                )
                assert started["turn_detection"]["semantic_fallback_active"] is False
                frame = base64.b64encode(b"\x00" * 1_280).decode("ascii")
                for sequence in range(2):
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "audio_frame",
                                "turn_id": "stream",
                                "sequence": sequence,
                                "data": frame,
                            }
                        )
                    )
                speech = _recv_until(ws, "speech_detected")
                assert speech["vad_provider"] == "test_neural_vad"
                assert speech["turn_id"]

                for sequence in range(2, 14):
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "audio_frame",
                                "turn_id": "stream",
                                "sequence": sequence,
                                "data": frame,
                            }
                        )
                    )
                endpoint = _recv_until(ws, "endpoint_detected", max_messages=40)
                assert endpoint["reason"] == "semantic_silence"
                assert endpoint["silence_ms"] == 440
                assert endpoint["endpointing"]["decision"] == "likely_complete"
                assert (
                    endpoint["endpointing"]["classifier_provider"]
                    == "multilingual_semantic_local"
                )
                final = _recv_until(ws, "transcript_final", max_messages=40)
                assert final["endpoint"]["completion_probability"] >= 0.72
                assert final["endpoint"]["semantic"]["recommended_wait_ms"] == 440
                mock_stt.on_speech_start.assert_awaited_once()
                mock_stt.on_speech_end.assert_awaited_once()
                ws.send_text(json.dumps({"type": "end"}))


def test_ws_new_speech_cancels_prior_stt_finalization():
    class ProbabilitySequence:
        name = "test_neural_vad"

        def __init__(self):
            self.values = [0.9, 0.9] + [0.05] * 12 + [0.9, 0.9]

        def score(self, _pcm):
            return self.values.pop(0) if self.values else 0.9

    class SlowFinalSTT:
        def __init__(self):
            self.cancelled = threading.Event()

        async def on_speech_start(self):
            return None

        async def feed_audio(self, _pcm):
            return STTPartial(
                text="This turn is complete.",
                confidence=0.95,
                language="en",
                stability=0.95,
                audio_ms=400,
            )

        async def on_speech_end(self):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

        def consume_metrics(self):
            return {}

        def reset(self):
            return None

    detector = HybridTurnDetector(speech_provider=ProbabilitySequence())
    first_stt = SlowFinalSTT()
    second_stt = SlowFinalSTT()
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-phase4-cancel-final@example.com")
    user = _make_user(user_id)

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch("app.routers.ws_session.HybridTurnDetector", return_value=detector),
        patch(
            "app.routers.ws_session.get_streaming_stt",
            side_effect=[first_stt, second_stt],
        ),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                json.loads(ws.receive_text())
                frame = base64.b64encode(b"\x00" * 1_280).decode("ascii")
                for sequence in range(14):
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "audio_frame",
                                "turn_id": "stream",
                                "sequence": sequence,
                                "data": frame,
                            }
                        )
                    )
                _recv_until(ws, "endpoint_detected", max_messages=60)
                for sequence in range(14, 16):
                    ws.send_text(
                        json.dumps(
                            {
                                "type": "audio_frame",
                                "turn_id": "stream",
                                "sequence": sequence,
                                "data": frame,
                            }
                        )
                    )
                second_speech = _recv_until(ws, "speech_detected", max_messages=60)
                assert second_speech["pause_kind"] == "interrupted"
                assert first_stt.cancelled.wait(timeout=1)
                ws.send_text(json.dumps({"type": "end"}))


async def _sentence_before_complete_stream(*_args, **_kwargs):
    yield {"type": "context_ready", "metrics": {"context_items_count": 1}}
    yield {"type": "reply_delta", "text": "First sentence."}
    yield {"type": "sentence_ready", "text": "First sentence."}
    await asyncio.sleep(0.02)
    yield {
        "type": "turn_complete",
        "reply": "First sentence.",
        "metrics": {"first_token_ms": 2},
    }


def test_ws_sentence_ready_starts_tts_before_turn_complete():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-tts@example.com")
    user = _make_user(user_id)

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
        patch(
            "app.routers.ws_session.run_voice_turn_stream",
            new=_sentence_before_complete_stream,
        ),
        patch("app.routers.ws_session.synthesize_stream", side_effect=_fake_tts_stream),
        patch("app.routers.ws_session._rate_limiter") as mock_rl,
    ):
        mock_rl.allow.return_value = True
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as ws:
                json.loads(ws.receive_text())
                ws.send_text(
                    json.dumps(
                        {"type": "text_turn", "text": "hello", "turn_id": "tts-turn"}
                    )
                )
                saw_tts = False
                saw_complete = False
                for _ in range(30):
                    msg = json.loads(ws.receive_text())
                    if msg.get("type") == "tts_chunk":
                        saw_tts = True
                        assert msg["chunk_index"] == 0
                        assert msg["is_final"] is False
                    if msg.get("type") == "tts_complete":
                        saw_complete = True
                        assert msg["is_final"] is True
                    if msg.get("type") == "turn_complete":
                        assert saw_tts is True
                        assert saw_complete is True
                        break
                    if msg.get("type") == "error":
                        pytest.fail(msg.get("message"))
                else:
                    pytest.fail("Did not receive turn_complete")
                ws.send_text(json.dumps({"type": "end"}))


def test_ws_session_survives_reconnect_with_session_id():
    user_id = uuid.uuid4()
    token = create_access_token(user_id, "ws-reconnect@example.com")
    user = _make_user(user_id)
    session_id = uuid.uuid4()

    with (
        _mock_ws_db(),
        patch(
            "app.routers.ws_session._user_from_token",
            new_callable=AsyncMock,
            return_value=user,
        ),
    ):
        with TestClient(app) as client:
            with client.websocket_connect(
                f"/api/v2/ws/session?token={token}&session_id={session_id}"
            ) as ws:
                started = json.loads(ws.receive_text())
                assert started["session_id"] == str(session_id)
                ws.send_text(json.dumps({"type": "end"}))
