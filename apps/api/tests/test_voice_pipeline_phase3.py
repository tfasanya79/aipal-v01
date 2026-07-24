from __future__ import annotations

import statistics
import time
import uuid

import pytest

from app.config import Settings
from app.conversation.contracts import ConversationInput, InputModality
from app.conversation.state import conversation_state_manager
from app.db import async_session
from app.models import User
from app.services.voice_transport import VoiceAudioIngress, audio_format_is_supported
from app.services.whisper_streaming_stt import WhisperStreamingSTT


def test_audio_contract_rejects_wrong_format_and_oversized_frame():
    assert audio_format_is_supported(
        {"encoding": "pcm_s16le", "sample_rate": 16_000, "channels": 1}
    )
    assert not audio_format_is_supported(
        {"encoding": "pcm_s16le", "sample_rate": 48_000, "channels": 1}
    )
    ingress = VoiceAudioIngress(max_utterance_ms=30_000)
    ingress.start("turn")
    rejected = ingress.accept(turn_id="turn", sequence=0, pcm=b"x" * (64 * 1024 + 1))
    assert not rejected.accepted
    assert rejected.reason == "frame_too_large"


def test_audio_ingress_enforces_bounded_utterance_memory():
    ingress = VoiceAudioIngress(max_utterance_ms=40)
    ingress.start("turn")
    assert ingress.accept(turn_id="turn", sequence=0, pcm=b"x" * 1_280).accepted
    rejected = ingress.accept(turn_id="turn", sequence=1, pcm=b"x")
    assert not rejected.accepted
    assert rejected.reason == "utterance_too_large"


def test_audio_ingress_p95_is_below_phase3_budget_under_load():
    ingress = VoiceAudioIngress(max_utterance_ms=30_000)
    ingress.start("load-turn")
    samples = []
    for sequence in range(500):
        started = time.perf_counter()
        accepted = ingress.accept(
            turn_id="load-turn",
            sequence=sequence,
            pcm=b"\x00" * 640,
        )
        samples.append((time.perf_counter() - started) * 1_000)
        assert accepted.accepted
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 0.5, f"audio ingress p95 {p95:.3f}ms exceeds 0.5ms"


def test_partial_inference_interval_adapts_to_utterance_length():
    stt = WhisperStreamingSTT(Settings(whisper_stream_partial_interval_ms=300))
    stt._buffer.extend(b"\x00" * (16_000 * 2))
    assert stt._adaptive_partial_interval_ms() == 180
    stt._buffer.extend(b"\x00" * (16_000 * 2 * 2))
    assert stt._adaptive_partial_interval_ms() == 300
    stt._buffer.extend(b"\x00" * (16_000 * 2 * 4))
    assert stt._adaptive_partial_interval_ms() == 450


@pytest.mark.asyncio
async def test_live_voice_stt_metadata_is_persisted_in_canonical_state():
    async with async_session() as db:
        user = User(email=f"phase3-state-{uuid.uuid4()}@example.com", timezone="UTC")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        conversation_id = uuid.uuid4()
        request = ConversationInput(
            user_id=user.id,
            conversation_id=conversation_id,
            turn_id="voice-state-turn",
            modality=InputModality.LIVE_VOICE,
            text="hello there",
            source_context={
                "stt": {
                    "stt_confidence": 0.87,
                    "stt_language": "en",
                    "audio_ms": 920,
                }
            },
        )
        state = await conversation_state_manager.begin_turn(db, request)

    assert state is not None
    assert state.current_turn_id == "voice-state-turn"
    assert state.final_transcript == "hello there"
    assert state.final_confidence == 0.87
    assert state.language == "en"
