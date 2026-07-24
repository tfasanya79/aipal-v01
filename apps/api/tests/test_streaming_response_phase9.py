from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.conversation.contracts import InputModality
from app.conversation.service import stream_conversation
from app.db import async_session
from app.llm_provider import _ollama_chat_stream
from app.main import app
from app.models import Message, User
from app.routers.ws_session import _run_turn_pipeline
from app.services.ai_reasoning_engine import stream_reasoned_final_response
from app.services.streaming_response import SpeechSegmenter
from app.voice_pipeline import TurnCancellationRegistry
from app.conversation.reasoning import ReasoningDecision


def _decision() -> ReasoningDecision:
    return ReasoningDecision.model_validate(
        {
            "schema_version": "1.0",
            "intents": [{"name": "general_conversation", "confidence": 0.95}],
            "primary_intent": "general_conversation",
            "missing_information": [],
            "mode": "companion",
            "emotion": {"emotion": "neutral", "intensity": 1, "urgency": 0},
            "conversation_strategy": "Answer directly.",
            "response_strategy": "Use a natural concise response.",
            "planning_notes": [],
            "tool_calls": [],
            "confirmation_message": None,
            "pending_action_resolution": "none",
        }
    )


async def _client(email: str) -> tuple[AsyncClient, dict[str, str]]:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    registration = await client.post("/api/v2/auth/register", json={"email": email})
    verification = await client.post(
        "/api/v2/auth/verify",
        json={"token": registration.json()["dev_token"]},
    )
    return client, {"Authorization": f"Bearer {verification.json()['access_token']}"}


def test_speech_segmenter_emits_clauses_before_complete_sentences_without_loss():
    segmenter = SpeechSegmenter(min_chars=20, max_chars=80)
    original = (
        "I can help you sort this out, starting with the urgent item; "
        "then we can handle the rest tomorrow."
    )
    segments: list[str] = []
    for chunk in ("I can help ", "you sort this out, starting ", "with the urgent item; then ", "we can handle the rest tomorrow."):
        segments.extend(segmenter.push(chunk))
    segments.extend(segmenter.flush())

    assert len(segments) >= 3
    assert segments[0].endswith(",")
    assert any(segment.endswith(";") for segment in segments)
    assert " ".join(segments) == original


def test_speech_segmenter_forces_bounded_word_safe_segments_and_flushes_once():
    segmenter = SpeechSegmenter(min_chars=16, max_chars=42)
    text = "This deliberately long phrase has no punctuation but still needs bounded speech chunks for playback"
    segments = segmenter.push(text) + segmenter.flush()

    assert all(len(segment) <= 42 for segment in segments)
    assert " ".join(segments) == text
    assert segmenter.flush() == []


@pytest.mark.asyncio
async def test_reasoned_final_response_forwards_provider_chunks_unchanged():
    calls: list[list[dict[str, str]]] = []

    async def provider(messages, **_kwargs):
        calls.append(messages)
        yield "First useful phrase, "
        yield "followed by the answer."

    chunks = [
        chunk
        async for chunk in stream_reasoned_final_response(
            user_message="Help me decide.",
            output_channel="voice",
            decision=_decision(),
            tool_results=[],
            context_items=[],
            conversation_history=[],
            user_preferences={},
            confirmation_required=False,
            confirmation_message=None,
            validation_errors=[],
            llm_stream=provider,
        )
    ]

    assert chunks == ["First useful phrase, ", "followed by the answer."]
    assert "Response purpose: final_response" in calls[0][0]["content"]
    assert "Output channel: voice" in calls[0][0]["content"]


@pytest.mark.asyncio
async def test_provider_failure_after_partial_stream_does_not_duplicate_fallback_text():
    client, headers = await _client("phase9-partial-failure@example.com")

    async def broken_stream(_messages, **_kwargs):
        yield "I can help with the first step,"
        raise RuntimeError("provider disconnected")

    try:
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                return_value=json.dumps(_decision().model_dump(mode="json")),
            ),
            patch(
                "app.services.reasoned_turn_service.llm_chat_stream",
                new=broken_stream,
            ),
        ):
            settings.return_value.ai_reasoning_enabled = True
            settings.return_value.ai_streaming_enabled = True
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Help me start.", "source": "voice"},
            )
        assert response.status_code == 200
        assert response.json()["reply"] == "I can help with the first step,"
        assert "I’m with you" not in response.json()["reply"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cancellation_closes_stream_quickly_and_does_not_persist_partial_reply():
    email = "phase9-cancel@example.com"
    client, _headers = await _client(email)
    conversation_id = uuid.uuid4()
    first_delta = asyncio.Event()
    release_provider = asyncio.Event()

    async def slow_stream(_messages, **_kwargs):
        yield "A partial response that must not persist,"
        first_delta.set()
        await release_provider.wait()
        yield " stale continuation."

    try:
        async with async_session() as db:
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one()
            cancel_event = asyncio.Event()

            async def consume() -> None:
                async for _event in stream_conversation(
                    db,
                    user,
                    "Give me a cancellable response.",
                    modality=InputModality.LIVE_VOICE,
                    conversation_id=conversation_id,
                    cancel_event=cancel_event,
                ):
                    pass

            with (
                patch("app.services.companion_orchestrator.get_settings") as settings,
                patch(
                    "app.services.companion_response_service.llm_chat",
                    new_callable=AsyncMock,
                    return_value=json.dumps(_decision().model_dump(mode="json")),
                ),
                patch(
                    "app.services.reasoned_turn_service.llm_chat_stream",
                    new=slow_stream,
                ),
            ):
                settings.return_value.ai_reasoning_enabled = True
                settings.return_value.ai_streaming_enabled = True
                task = asyncio.create_task(consume())
                await asyncio.wait_for(first_delta.wait(), timeout=1)
                started = time.perf_counter()
                cancel_event.set()
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                cancellation_ms = (time.perf_counter() - started) * 1_000

            rows = list(
                (
                    await db.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars()
            )
        assert cancellation_ms < 100
        assert rows == []
    finally:
        release_provider.set()
        await client.aclose()


@pytest.mark.asyncio
async def test_ollama_provider_uses_ndjson_stream_and_closes_connection():
    closed = False

    class Response:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            nonlocal closed
            closed = True

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield json.dumps({"message": {"content": "Hello "}, "done": False})
            yield "not-json"
            yield json.dumps({"message": {"content": "there."}, "done": True})

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, *_args, **_kwargs):
            return Response()

    with patch("app.llm_provider.httpx.AsyncClient", return_value=Client()):
        chunks = [
            chunk
            async for chunk in _ollama_chat_stream(
                [{"role": "user", "content": "hello"}],
                max_tokens=24,
            )
        ]

    assert chunks == ["Hello ", "there."]
    assert closed is True


class _WebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.messages.append(dict(payload))


@pytest.mark.asyncio
async def test_voice_pipeline_overlaps_generation_and_incremental_tts_then_drains():
    websocket = _WebSocket()
    tts_started = asyncio.Event()
    generation_finished = False

    async def voice_stream(*_args, **_kwargs):
        nonlocal generation_finished
        yield {"type": "context_ready", "mode": "companion", "metrics": {}}
        yield {"type": "reply_delta", "text": "This is the first useful phrase, "}
        yield {"type": "speech_segment_ready", "text": "This is the first useful phrase,"}
        await asyncio.wait_for(tts_started.wait(), timeout=0.5)
        assert generation_finished is False
        yield {"type": "reply_delta", "text": "and this is the second."}
        yield {"type": "speech_segment_ready", "text": "and this is the second."}
        generation_finished = True
        yield {
            "type": "turn_complete",
            "reply": "This is the first useful phrase, and this is the second.",
            "mode": "companion",
            "tool_actions": [],
            "suggested_actions": [],
        }

    async def tts_stream(_text, voice=None):
        del voice
        tts_started.set()
        await asyncio.sleep(0)
        yield b"decodable-audio", "audio/mpeg"

    @asynccontextmanager
    async def session():
        yield object()

    with (
        patch("app.routers.ws_session.async_session", side_effect=session),
        patch("app.routers.ws_session.run_voice_turn_stream", new=voice_stream),
        patch("app.routers.ws_session.synthesize_stream", new=tts_stream),
        patch("app.routers.ws_session.mark_ai_speaking", new_callable=AsyncMock),
        patch("app.routers.ws_session.mark_listening", new_callable=AsyncMock),
    ):
        await _run_turn_pipeline(
            websocket,  # type: ignore[arg-type]
            SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
            uuid.uuid4(),
            "phase9-turn",
            "Help me think.",
            TurnCancellationRegistry(),
        )

    types = [message["type"] for message in websocket.messages]
    assert types.count("tts_chunk") == 2
    assert types.index("tts_chunk") < types.index("turn_complete")
    assert types.index("tts_complete") < types.index("turn_complete")
    chunks = [message["chunk_index"] for message in websocket.messages if message["type"] == "tts_chunk"]
    assert chunks == [0, 1]
    terminal = next(message for message in websocket.messages if message["type"] == "turn_complete")
    assert terminal["metrics"]["speech_segment_count"] == 2
    assert terminal["metrics"]["tts_chunk_count"] == 2


@pytest.mark.asyncio
async def test_tts_worker_failure_propagates_without_queue_deadlock():
    websocket = _WebSocket()

    async def voice_stream(*_args, **_kwargs):
        yield {"type": "context_ready", "mode": "companion", "metrics": {}}
        for index in range(1):
            yield {"type": "reply_delta", "text": f"segment {index}, "}
            yield {"type": "speech_segment_ready", "text": f"segment {index},"}
        yield {"type": "turn_complete", "reply": "done", "mode": "companion"}

    async def failed_tts(_text, voice=None):
        del voice
        raise RuntimeError("tts failed")
        yield b"", "audio/mpeg"

    @asynccontextmanager
    async def session():
        yield object()

    with (
        patch("app.routers.ws_session.async_session", side_effect=session),
        patch("app.routers.ws_session.run_voice_turn_stream", new=voice_stream),
        patch("app.routers.ws_session.synthesize_stream", new=failed_tts),
    ):
        await asyncio.wait_for(
            _run_turn_pipeline(
                websocket,  # type: ignore[arg-type]
                SimpleNamespace(id=uuid.uuid4()),  # type: ignore[arg-type]
                uuid.uuid4(),
                "phase9-tts-failure",
                "Test failure.",
                TurnCancellationRegistry(),
            ),
            timeout=0.5,
        )
    terminal = next(
        message for message in websocket.messages if message["type"] == "turn_complete"
    )
    assert terminal["reply"] == "done"
    assert terminal["metrics"]["tts_failed"] is True


def test_segmentation_latency_budget():
    samples: list[float] = []
    for _ in range(5_000):
        segmenter = SpeechSegmenter()
        started = time.perf_counter()
        segmenter.push("A useful streaming phrase, followed by another useful phrase.")
        segmenter.flush()
        samples.append((time.perf_counter() - started) * 1_000)
    assert statistics.quantiles(samples, n=20)[18] < 2


@pytest.mark.asyncio
async def test_concurrent_response_streams_preserve_per_turn_order():
    async def run(index: int) -> str:
        async def provider(_messages, **_kwargs):
            yield f"{index}:first|"
            await asyncio.sleep(0)
            yield f"{index}:second"

        chunks = [
            chunk
            async for chunk in stream_reasoned_final_response(
                user_message="Load test.",
                output_channel="voice",
                decision=_decision(),
                tool_results=[],
                context_items=[],
                conversation_history=[],
                user_preferences={},
                confirmation_required=False,
                confirmation_message=None,
                validation_errors=[],
                llm_stream=provider,
            )
        ]
        return "".join(chunks)

    results = await asyncio.gather(*(run(index) for index in range(100)))
    assert results == [f"{index}:first|{index}:second" for index in range(100)]


def test_no_buffered_canonical_adapter_or_competing_legacy_streamer():
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    adapter = (app_dir / "conversation" / "adapters.py").read_text(encoding="utf-8")
    orchestrator = (app_dir / "services" / "companion_orchestrator.py").read_text(encoding="utf-8")
    response_service = (app_dir / "services" / "companion_response_service.py").read_text(encoding="utf-8")
    websocket = (app_dir / "routers" / "ws_session.py").read_text(encoding="utf-8")

    assert ".run_turn(" not in adapter
    assert "generate_companion_response_stream" not in orchestrator
    assert "generate_companion_response_stream" not in response_service
    assert "await _speak_sentence" not in websocket
