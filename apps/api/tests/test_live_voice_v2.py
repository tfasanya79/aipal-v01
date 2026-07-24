"""Live Voice v2 unit tests."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from app.services.stt_provider import STTFinal
from app.services.voice_transport import VoiceAudioIngress
from app.voice_pipeline import (
    TurnCancellationRegistry,
    split_sentences,
    strip_plan_json_block,
)


def test_split_sentences():
    complete, rest = split_sentences("Hello there. How are")
    assert complete == ["Hello there."]
    assert rest == "How are"
    complete2, rest2 = split_sentences("Done.", flush=True)
    assert complete2 == ["Done."]
    assert rest2 == ""


def test_strip_plan_json_block():
    text = 'Sure thing.\n```json\n{"intent":"plan_day","proposed_tasks":[]}\n```'
    visible, raw = strip_plan_json_block(text)
    assert "Sure thing" in visible
    assert raw is not None
    assert "plan_day" in raw


@pytest.mark.asyncio
async def test_turn_cancellation_registry():
    reg = TurnCancellationRegistry()

    async def slow():
        await asyncio.sleep(10)

    task = asyncio.create_task(slow())
    cancel_event = asyncio.Event()
    reg.register("t1", task, cancel_event=cancel_event)
    assert reg.cancel("t1") is True
    assert cancel_event.is_set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_whisper_streaming_stt_buffers_only_during_speech():
    from app.services.whisper_streaming_stt import WhisperStreamingSTT
    from app.config import Settings

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)

    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    ignored = await stt.feed_audio(pcm)
    assert ignored is None
    assert len(stt._buffer) == 0

    await stt.on_speech_start()
    buffered = await stt.feed_audio(pcm)
    assert buffered is None
    assert len(stt._buffer) == len(pcm)


@pytest.mark.asyncio
async def test_whisper_streaming_stt_emits_partial_without_blocking_feed():
    from app.services.whisper_streaming_stt import WhisperStreamingSTT
    from app.config import Settings

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    async def fake_transcribe(*, beam_size):
        await asyncio.sleep(0)
        return "I need to schedule", {
            "stt_confidence": 0.88,
            "stt_language": "en",
            "stt_language_confidence": 0.96,
        }

    with patch.object(stt, "_transcribe_with_meta", side_effect=fake_transcribe):
        await stt.on_speech_start()
        first = await stt.feed_audio(pcm)
        assert first is None
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        partial = await stt.feed_audio(pcm)
        assert partial.text == "I need to schedule"
        assert partial.confidence == 0.88
        assert partial.language == "en"
        assert partial.language_confidence == 0.96
        assert stt.consume_metrics()["stt_partial_ms"] >= 0


@pytest.mark.asyncio
async def test_whisper_streaming_stt_on_speech_end_transcribes():
    from app.services.whisper_streaming_stt import WhisperStreamingSTT
    from app.config import Settings

    settings = Settings(whisper_stream_partial_interval_ms=0)
    stt = WhisperStreamingSTT(settings)
    pcm = (np.zeros(16000, dtype=np.int16)).tobytes()

    with patch.object(stt, "_transcribe_with_meta", new_callable=AsyncMock) as mock_tx:
        mock_tx.return_value = (
            "hello",
            {"stt_confidence": 0.9, "stt_language": "en"},
        )
        await stt.on_speech_start()
        await stt.feed_audio(pcm)
        result = await stt.on_speech_end()
        assert result == STTFinal(
            text="hello",
            confidence=0.9,
            language="en",
            languages=["en"],
            sequence=0,
            audio_ms=1000,
        )
        mock_tx.assert_awaited()


def test_voice_audio_ingress_deduplicates_and_reports_sequence_gaps():
    ingress = VoiceAudioIngress(max_utterance_ms=1_000)
    ingress.start("turn-1")

    assert ingress.accept(turn_id="turn-1", sequence=0, pcm=b"a" * 640).accepted
    duplicate = ingress.accept(turn_id="turn-1", sequence=0, pcm=b"a" * 640)
    assert duplicate.duplicate is True
    assert ingress.accept(turn_id="turn-1", sequence=2, pcm=b"b" * 640).accepted
    assert not ingress.accept(turn_id="other", sequence=3, pcm=b"c").accepted

    metrics = ingress.finish("turn-1")
    assert metrics["audio_frames"] == 2
    assert metrics["audio_duplicate_frames"] == 1
    assert metrics["audio_sequence_gaps"] == 1
    assert metrics["audio_ms"] == 40


@pytest.mark.asyncio
async def test_run_voice_turn_stream_yields_deltas():
    from app.services.voice_turn import run_voice_turn_stream

    user = MagicMock()
    user.id = "user-1"
    user.timezone = "UTC"
    user.wake_name = "Alex"
    user.display_name = "Alex"
    user.about_me = None

    db = AsyncMock()

    async def fake_stream(*_args, **_kwargs):
        payloads = [
            {"type": "context_ready", "metrics": {"context_items_count": 1}},
            {"type": "reply_delta", "text": "Hi ", "metrics": {"first_token_ms": 1}},
            {"type": "reply_delta", "text": "there.", "metrics": {"first_token_ms": 1}},
            {"type": "sentence_ready", "text": "Hi there."},
            {
                "type": "turn_complete",
                "reply": "Hi there.",
                "mode": "companion",
                "emotion": {"emotion": "neutral", "intensity": 1, "context": "ok"},
                "memories_used": [],
                "suggested_actions": [],
                "plan_draft": None,
                "requires_confirmation": False,
                "confirmation_prompt": None,
                "conversation_id": str(uuid.uuid4()),
                "metrics": {"first_token_ms": 1},
            },
        ]
        for payload in payloads:
            event = MagicMock()
            event.to_transport.return_value = payload
            yield event

    with patch("app.services.voice_turn.stream_conversation", new=fake_stream):
        events = []
        async for ev in run_voice_turn_stream(db, user, "hi", "sess-1"):
            events.append(ev)
        deltas = [e for e in events if e["type"] == "reply_delta"]
        assert "".join(d["text"] for d in deltas) == "Hi there."
        assert deltas[0]["metrics"]["first_reply_delta_ms"] >= 0
        meta = [e for e in events if e["type"] == "turn_complete"]
        assert meta and meta[0]["reply"]
        assert "turn_total_ms" in meta[0]["metrics"]


@pytest.mark.asyncio
async def test_llm_chat_stream_deepseek_parses_sse():
    from app.llm_provider import llm_chat_stream

    lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        "data: [DONE]",
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class FakeStream:
        async def __aenter__(self):
            return FakeResp()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def stream(self, *args, **kwargs):
            return FakeStream()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    with patch("app.llm_provider.settings") as mock_settings:
        mock_settings.llm_provider = "deepseek"
        mock_settings.deepseek_api_key = "test-key"
        with patch("app.llm_provider.httpx.AsyncClient", return_value=FakeClient()):
            chunks = []
            async for c in llm_chat_stream([
                {"role": "system", "content": "# Canonical runtime contract v2.0"},
                {"role": "user", "content": "hi"},
            ]):
                chunks.append(c)
            assert chunks == ["Hello"]


@pytest.mark.asyncio
async def test_llm_chat_openai_compatible_uses_configured_endpoint():
    from app.llm_provider import llm_chat

    captured = {}

    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "OpenAI hello"}}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    with patch("app.llm_provider.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        mock_settings.openai_api_key = "test-openai-key"
        mock_settings.openai_base_url = "https://api.openai.com/v1"
        mock_settings.openai_model = "gpt-test"
        with patch("app.llm_provider.httpx.AsyncClient", return_value=FakeClient()):
            reply = await llm_chat([
                {"role": "system", "content": "# Canonical runtime contract v2.0"},
                {"role": "user", "content": "hi"},
            ])

    assert reply == "OpenAI hello"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["kwargs"]["headers"]["Authorization"] == "Bearer test-openai-key"
    assert captured["kwargs"]["json"]["model"] == "gpt-test"


@pytest.mark.asyncio
async def test_llm_chat_stream_openai_compatible_parses_sse():
    from app.llm_provider import llm_chat_stream

    lines = [
        'data: {"choices":[{"delta":{"content":"Hi"}}]}',
        'data: {"choices":[{"delta":{"content":" there"}}]}',
        "data: [DONE]",
    ]

    class FakeResp:
        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

    class FakeStream:
        async def __aenter__(self):
            return FakeResp()

        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def stream(self, *args, **kwargs):
            return FakeStream()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

    with patch("app.llm_provider.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        mock_settings.openai_api_key = "test-openai-key"
        mock_settings.openai_base_url = "https://api.openai.com/v1"
        mock_settings.openai_model = "gpt-test"
        with patch("app.llm_provider.httpx.AsyncClient", return_value=FakeClient()):
            chunks = []
            async for c in llm_chat_stream([
                {"role": "system", "content": "# Canonical runtime contract v2.0"},
                {"role": "user", "content": "hi"},
            ]):
                chunks.append(c)

    assert chunks == ["Hi", " there"]
