import asyncio
import base64
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import jwt
from jwt import PyJWTError as JWTError
from sqlalchemy import select

from ..config import get_settings
from ..db import async_session
from ..models import Conversation, LiveSession, User
from ..services.stt_provider import (
    STTFinal,
    STTPartial,
    StreamingSTT,
    get_streaming_stt,
)
from ..services.turn_detection import (
    EndpointContext,
    HybridTurnDetector,
    TurnDetectionEvent,
    TurnSignal,
)
from ..services.voice_transport import (
    PCM_CHANNELS,
    PCM_SAMPLE_RATE,
    VOICE_PROTOCOL_VERSION,
    VoiceAudioIngress,
    audio_format_is_supported,
)
from ..services.voice_turn import preload_voice_context, run_voice_turn_stream
from ..services.conversation_state_manager import (
    mark_ai_speaking,
    mark_interrupted,
    mark_listening,
    mark_user_speaking,
)
from ..conversation.state import conversation_state_manager
from ..tts import synthesize_stream
from ..voice_pipeline import TurnCancellationRegistry, TurnRateLimiter

router = APIRouter()
log = logging.getLogger("aipal.ws")
settings = get_settings()

_rate_limiter = TurnRateLimiter(settings.live_turns_per_minute)


async def _user_from_token(token: str) -> User | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, ValueError):
        return None
    async with async_session() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()


async def _send_state(websocket: WebSocket, state: str) -> None:
    await websocket.send_json({"type": "state", "state": state})


async def _send_turn_failed(
    websocket: WebSocket,
    *,
    turn_id: str,
    stage: str,
    reason_code: str,
    user_message: str,
    retryable: bool = True,
    conversation_id: str | None = None,
) -> None:
    await websocket.send_json(
        {
            "type": "turn_failed",
            "event": "turn_failed",
            "conversation_id": conversation_id,
            "turn_id": turn_id,
            "stage": stage,
            "reason_code": reason_code,
            "retryable": retryable,
            "user_message": user_message,
            "diagnostic_id": str(uuid.uuid4()),
        }
    )


def _supported_endpoint_languages() -> list[str]:
    raw = str(get_settings().semantic_endpointing_supported_languages or "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _topic_classifier_diagnostics(settings: Any) -> dict[str, Any]:
    from ..conversation.topic_transition import get_topic_classifier

    classifier = get_topic_classifier()
    return {
        "provider": classifier.provider,
        "model": classifier.model_name,
        "version": classifier.model_version,
        "device": settings.topic_classifier_device,
        "fallback_active": classifier.fallback_active,
        "max_paused_topics": settings.topic_classifier_max_paused_topics,
        "latency_summary": classifier.latency_summary(),
    }


def _safe_language(value: str | None) -> str:
    text = str(value or "").strip()
    return text if text else "unknown"


def _safe_languages(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return ["unknown"]
    languages = [_safe_language(item) for item in values if _safe_language(item) != "unknown"]
    return languages or ["unknown"]


async def _preload_context_for_turn(
    user: User, session_id: uuid.UUID, turn_id: str, started_at: float
) -> dict:
    async with async_session() as db:
        return await preload_voice_context(
            db,
            user,
            str(session_id),
            partial_message="",
            speech_start_started_at=started_at,
        )


async def _run_turn_pipeline(
    websocket: WebSocket,
    user: User,
    session_id: uuid.UUID,
    turn_id: str,
    text: str,
    cancel_registry: TurnCancellationRegistry,
    *,
    stt_final_ms: int | None = None,
    stt_metrics: dict[str, Any] | None = None,
    preload_task: asyncio.Task | None = None,
    on_playback_started: Callable[[str], None] | None = None,
) -> None:
    cancel_event = asyncio.Event()
    pipeline_started = time.monotonic()
    metrics: dict[str, Any] = {}
    if stt_final_ms is not None:
        metrics["stt_final_ms"] = stt_final_ms
    if stt_metrics:
        metrics.update(stt_metrics)

    async def _pipeline() -> None:
        tts_queue: asyncio.Queue[str | None] = asyncio.Queue(
            maxsize=max(1, min(settings.ai_tts_queue_size, 16))
        )
        send_lock = asyncio.Lock()
        worker_task: asyncio.Task | None = None
        chunk_index = 0
        tts_started_at: float | None = None
        first_segment_at: float | None = None
        terminal: dict[str, Any] | None = None
        voice_profile = "calm_female"
        tts_failed = False

        async def send(payload: dict[str, Any]) -> None:
            async with send_lock:
                await websocket.send_json(payload)

        async def record_tts_failure() -> None:
            nonlocal tts_failed
            if worker_task is None:
                return
            try:
                await worker_task
            except Exception as exc:
                tts_failed = True
                metrics["tts_failed"] = True
                metrics["tts_failure"] = type(exc).__name__
                log.warning(
                    "streaming_tts_failed turn=%s failure=%s",
                    turn_id,
                    type(exc).__name__,
                )

        async def enqueue_speech(segment: str | None) -> bool:
            nonlocal tts_failed
            if tts_failed:
                return False
            if worker_task is not None and worker_task.done():
                await record_tts_failure()
                return not tts_failed
            put_task = asyncio.create_task(tts_queue.put(segment))
            if worker_task is None:
                await put_task
                return True
            done, _pending = await asyncio.wait(
                {put_task, worker_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if worker_task in done and not put_task.done():
                put_task.cancel()
                await asyncio.gather(put_task, return_exceptions=True)
                await record_tts_failure()
                return not tts_failed
            await put_task
            return True

        async def tts_worker() -> None:
            nonlocal chunk_index, tts_started_at
            while True:
                segment = await tts_queue.get()
                try:
                    if segment is None or cancel_event.is_set():
                        return
                    await send(
                        {
                            "type": "sentence_ready",
                            "turn_id": turn_id,
                            "text": segment,
                        }
                    )
                    segment_started = time.monotonic()
                    metrics["speech_segment_count"] = int(
                        metrics.get("speech_segment_count", 0)
                    ) + 1
                    async for audio, mime in synthesize_stream(
                        segment,
                        voice=voice_profile,
                    ):
                        if cancel_event.is_set():
                            return
                        if not audio:
                            continue
                        now = time.monotonic()
                        if tts_started_at is None:
                            tts_started_at = now
                            metrics["first_tts_chunk_ms"] = int(
                                (now - pipeline_started) * 1000
                            )
                            metrics["speech_segment_to_first_tts_ms"] = int(
                                (now - (first_segment_at or segment_started)) * 1000
                            )
                            if on_playback_started is not None:
                                on_playback_started(turn_id)
                            await mark_ai_speaking(
                                str(user.id),
                                str(session_id),
                                turn_id=turn_id,
                            )
                        payload = {
                            "type": "tts_chunk",
                            "turn_id": turn_id,
                            "chunk_index": chunk_index,
                            "is_final": False,
                            "text": segment,
                            "data": base64.b64encode(audio).decode("ascii"),
                            "mime": mime,
                        }
                        chunk_index += 1
                        metrics["tts_chunk_count"] = chunk_index
                        await send(payload)
                finally:
                    tts_queue.task_done()

        turn_completed_sent = False

        try:
            preloaded_context = None
            if preload_task is not None:
                try:
                    preloaded_context = await preload_task
                    user_preferences = (preloaded_context or {}).get(
                        "user_preferences"
                    ) or {}
                    voice_profile = str(
                        user_preferences.get("voice_profile")
                        or user_preferences.get("tts_voice")
                        or voice_profile
                    )
                except Exception:
                    log.exception("voice_context_preload_failed turn=%s", turn_id)

            worker_task = asyncio.create_task(
                tts_worker(),
                name=f"tts-stream-{turn_id}",
            )
            async with async_session() as db:
                async for event in run_voice_turn_stream(
                    db,
                    user,
                    text,
                    str(session_id),
                    turn_id=turn_id,
                    stt_metadata=stt_metrics,
                    cancel_event=cancel_event,
                    preloaded_context=preloaded_context,
                ):
                    if cancel_event.is_set():
                        raise asyncio.CancelledError
                    etype = str(event.get("type") or "")
                    metrics.update(event.get("metrics") or {})
                    if etype == "context_ready":
                        voice_profile = str(event.get("voice_profile") or voice_profile)
                        await send(
                            {
                                "type": "context_ready",
                                "turn_id": turn_id,
                                "mode": event.get("mode"),
                                "emotion": event.get("emotion"),
                                "metrics": metrics,
                                "voice_profile": voice_profile,
                            }
                        )
                    elif etype == "reply_delta":
                        chunk = str(event.get("text") or "")
                        if chunk:
                            await send(
                                {
                                    "type": "reply_delta",
                                    "turn_id": turn_id,
                                    "text": chunk,
                                }
                            )
                    elif etype in {"speech_segment_ready", "sentence_ready"}:
                        segment = str(event.get("text") or "").strip()
                        if segment:
                            if first_segment_at is None:
                                first_segment_at = time.monotonic()
                                metrics["first_speech_segment_ms"] = int(
                                    (first_segment_at - pipeline_started) * 1000
                                )
                            wait_started = time.monotonic()
                            await enqueue_speech(segment)
                            metrics["tts_queue_wait_ms"] = int(
                                metrics.get("tts_queue_wait_ms", 0)
                            ) + int((time.monotonic() - wait_started) * 1000)
                    elif etype in {
                        "reasoning_complete",
                        "tool_started",
                        "tool_completed",
                        "post_processing_started",
                        "tool_suggestion",
                        "memory_suggestion",
                    }:
                        await send({"turn_id": turn_id, **event})
                    elif etype in {"turn_meta", "turn_complete"}:
                        terminal = event
                        metrics.update(event.get("reasoning_metrics") or {})
                        break

            if terminal is None or cancel_event.is_set():
                return
            payload = {
                "type": "turn_complete",
                "event": "assistant_message_completed",
                "turn_id": turn_id,
                "reply": terminal.get("reply", ""),
                "assistantMessage": terminal.get("reply", ""),
                "text": terminal.get("reply", ""),
                "speak": True,
                "voiceId": voice_profile,
                "uiState": "idle",
                "action": terminal.get("tool_actions", []),
                "todaySync": None,
                "tool_actions": terminal.get("tool_actions", []),
                "draft_confirmed": terminal.get("draft_confirmed", False),
                "mode": terminal.get("mode"),
                "emotion": terminal.get("emotion"),
                "memories_used": terminal.get("memories_used", []),
                "suggested_actions": terminal.get("suggested_actions", []),
                "requires_confirmation": terminal.get("requires_confirmation", False),
                "confirmation_prompt": terminal.get("confirmation_prompt"),
                "conversation_id": terminal.get("conversation_id"),
                "status": "completed",
                "metrics": metrics,
            }
            draft = terminal.get("plan_draft")
            if draft:
                payload["plan_draft"] = (
                    draft.model_dump() if hasattr(draft, "model_dump") else draft
                )
            await send(payload)
            turn_completed_sent = True
            closing_queued = await enqueue_speech(None)
            if closing_queued:
                join_task = asyncio.create_task(tts_queue.join())
                if worker_task is not None:
                    done, _pending = await asyncio.wait(
                        {join_task, worker_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if worker_task in done and not join_task.done():
                        join_task.cancel()
                        await asyncio.gather(join_task, return_exceptions=True)
                        await record_tts_failure()
                    else:
                        await join_task
                        await record_tts_failure()
                else:
                    await join_task
            if cancel_event.is_set():
                return
            await send(
                {
                    "type": "tts_complete",
                    "turn_id": turn_id,
                    "chunk_index": chunk_index,
                    "is_final": True,
                    "failed": tts_failed,
                }
            )
            log.info(
                "live_voice turn_complete user=%s session=%s turn=%s reply_len=%d metrics=%s",
                user.id,
                session_id,
                turn_id,
                len(terminal.get("reply", "") or ""),
                metrics,
            )
            await mark_listening(str(user.id), str(session_id))
            await send({"type": "state", "state": "listening"})
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        except Exception:
            cancel_event.set()
            log.exception("live_turn_pipeline_failed turn=%s", turn_id)
            if not turn_completed_sent:
                await _send_turn_failed(
                    websocket,
                    turn_id=turn_id,
                    conversation_id=str(session_id),
                    stage="orchestrator",
                    reason_code="orchestrator_error",
                    user_message="I couldn’t process that. Please try again.",
                )
                await mark_listening(str(user.id), str(session_id))
                await _send_state(websocket, "listening")
            raise
        finally:
            if worker_task is not None and not worker_task.done():
                worker_task.cancel()
                await asyncio.gather(worker_task, return_exceptions=True)
            while not tts_queue.empty():
                try:
                    tts_queue.get_nowait()
                    tts_queue.task_done()
                except asyncio.QueueEmpty:
                    break

    task = asyncio.create_task(_pipeline(), name=f"live-turn-{turn_id}")
    cancel_registry.register(turn_id, task, cancel_event=cancel_event)
    try:
        await asyncio.wait_for(task, timeout=float(settings.ai_reasoning_timeout_seconds))
    except TimeoutError:
        cancel_event.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await _send_turn_failed(
            websocket,
            turn_id=turn_id,
            conversation_id=str(session_id),
            stage="orchestrator",
            reason_code="orchestrator_timeout",
            user_message="The response took too long. Please try again.",
        )
        await mark_listening(str(user.id), str(session_id))
        await _send_state(websocket, "listening")
    except asyncio.CancelledError:
        cancel_event.set()
    finally:
        cancel_registry.clear(turn_id)


async def _finalize_detected_turn(
    websocket: WebSocket,
    user: User,
    session_id: uuid.UUID,
    turn_id: str,
    stt: StreamingSTT,
    cancel_registry: TurnCancellationRegistry,
    *,
    detection: TurnDetectionEvent,
    transport_metrics: dict[str, Any],
    preload_task: asyncio.Task | None,
    on_playback_started: Callable[[str], None],
) -> None:
    if not _rate_limiter.allow(str(user.id)):
        stt.reset()
        if preload_task:
            preload_task.cancel()
        await mark_listening(str(user.id), str(session_id))
        await websocket.send_json(
            {
                "type": "error",
                "turn_id": turn_id,
                "code": "voice_rate_limit",
                "message": "Rate limit exceeded; try again shortly.",
            }
        )
        await _send_state(websocket, "listening")
        return

    stt_t0 = time.monotonic()
    try:
        raw_final = await asyncio.wait_for(
            stt.on_speech_end(),
            timeout=max(1.0, float(settings.max_audio_decode_seconds)),
        )
    except TimeoutError:
        stt.reset()
        if preload_task:
            preload_task.cancel()
        await mark_listening(str(user.id), str(session_id))
        await _send_turn_failed(
            websocket,
            turn_id=turn_id,
            conversation_id=str(session_id),
            stage="final_stt",
            reason_code="stt_timeout",
            user_message="I couldn’t understand that in time. Please try again.",
        )
        await _send_state(websocket, "listening")
        return
    except Exception:
        stt.reset()
        if preload_task:
            preload_task.cancel()
        log.exception("live_voice_stt_failed turn=%s", turn_id)
        await mark_listening(str(user.id), str(session_id))
        await _send_turn_failed(
            websocket,
            turn_id=turn_id,
            conversation_id=str(session_id),
            stage="final_stt",
            reason_code="stt_provider_error",
            user_message="I couldn’t understand that. Please try again.",
        )
        await _send_state(websocket, "listening")
        return
    stt_metrics = stt.consume_metrics()
    final_result = (
        raw_final
        if isinstance(raw_final, STTFinal)
        else STTFinal(
            text=str(raw_final or ""),
            confidence=float(stt_metrics.get("stt_confidence", 0.0)),
            language=_safe_language(stt_metrics.get("stt_language")),
            language_confidence=float(
                stt_metrics.get("stt_language_confidence", 0.0) or 0.0
            ),
            languages=list(
                stt_metrics.get("stt_languages")
                if isinstance(stt_metrics.get("stt_languages"), (list, tuple))
                else [stt_metrics.get("stt_language") or "unknown"]
            ),
            code_switching_detected=bool(
                stt_metrics.get("stt_code_switching_detected", False)
            ),
        )
    )
    transcript = final_result.text.strip()
    stt_metrics.update(transport_metrics)
    stt_metrics.update(
        {
            "stt_final_ms": int((time.monotonic() - stt_t0) * 1_000),
            "turn_detection_silence_ms": detection.silence_ms,
            "turn_completion_probability": detection.completion_probability,
            "turn_endpoint_reason": detection.reason,
            "turn_pause_kind": detection.pause_kind.value
            if detection.pause_kind
            else None,
            "turn_vad_probability": detection.speech_probability,
        }
    )
    if detection.endpoint_decision is not None:
        stt_metrics.update(
            {
                "endpoint_decision": detection.endpoint_decision.decision.value,
                "endpoint_decision_confidence": detection.endpoint_decision.confidence,
                "endpoint_recommended_wait_ms": (
                    detection.endpoint_decision.recommended_wait_ms
                ),
                "endpoint_classifier_provider": (
                    detection.endpoint_decision.classifier_provider
                ),
                "endpoint_classifier_ms": (
                    detection.endpoint_decision.classifier_latency_ms
                ),
                "endpoint_recent_change_ratio": (
                    detection.endpoint_decision.recent_change_ratio
                ),
            }
    )
    stt_metrics.setdefault("stt_confidence", final_result.confidence)
    stt_metrics.setdefault("stt_language", _safe_language(final_result.language))
    final_audio_ms = final_result.audio_ms or int(stt_metrics.get("audio_ms", 0))
    await websocket.send_json(
        {
            "type": "transcript_final",
            "event": "final_transcript",
            "conversation_id": str(session_id),
            "turn_id": turn_id,
            "text": transcript,
            "confidence": final_result.confidence,
            "language": _safe_language(final_result.language),
            "language_confidence": final_result.language_confidence,
            "languages": _safe_languages(final_result.languages),
            "language_changed": final_result.language_changed,
            "code_switching_detected": final_result.code_switching_detected,
            "audio_ms": final_audio_ms,
            "no_speech_probability": final_result.no_speech_probability,
            "is_final": True,
            "endpoint": {
                "reason": detection.reason,
                "silence_ms": detection.silence_ms,
                "completion_probability": detection.completion_probability,
                "pause_kind": detection.pause_kind.value
                if detection.pause_kind
                else None,
                "semantic": (
                    detection.endpoint_decision.to_transport()
                    if detection.endpoint_decision
                    else None
                ),
            },
        }
    )
    if not transcript:
        if preload_task:
            preload_task.cancel()
        await mark_listening(str(user.id), str(session_id))
        await websocket.send_json(
            {
                "type": "transcription_failed",
                "event": "transcription_failed",
                "conversation_id": str(session_id),
                "turn_id": turn_id,
                "stage": "final_stt",
                "reason_code": "empty_final_transcript",
                "retryable": True,
                "user_message": "I couldn’t understand that. Please try again.",
                "diagnostic_id": str(uuid.uuid4()),
            }
        )
        await _send_state(websocket, "listening")
        return

    await _send_state(websocket, "thinking")
    await _run_turn_pipeline(
        websocket,
        user,
        session_id,
        turn_id,
        transcript,
        cancel_registry,
        stt_final_ms=int(stt_metrics["stt_final_ms"]),
        stt_metrics=stt_metrics,
        preload_task=preload_task,
        on_playback_started=on_playback_started,
    )


@router.websocket("/ws/session")
async def live_session(websocket: WebSocket):
    await websocket.accept()
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        return
    user = await _user_from_token(token)
    if not user:
        await websocket.close(code=4401)
        return

    requested_session = websocket.query_params.get("session_id")
    try:
        session_id = uuid.UUID(requested_session) if requested_session else uuid.uuid4()
    except ValueError:
        session_id = uuid.uuid4()
    async with async_session() as db:
        existing_live = await db.get(LiveSession, session_id)
        if existing_live is not None and existing_live.user_id != user.id:
            await websocket.close(code=4403)
            return
        if existing_live is None:
            db.add(LiveSession(id=session_id, user_id=user.id, state="active"))
        else:
            existing_live.state = "active"
            existing_live.ended_at = None
        existing_conv = await db.get(Conversation, session_id)
        if existing_conv is not None and existing_conv.user_id != user.id:
            await websocket.close(code=4403)
            return
        if existing_conv is None:
            db.add(
                Conversation(
                    id=session_id,
                    user_id=user.id,
                    mode="companion",
                    title="Live session",
                )
            )
        await db.commit()
        resumed_state = await conversation_state_manager.resume(
            db,
            user_id=user.id,
            conversation_id=session_id,
        )

    turn_detector = await asyncio.to_thread(
        HybridTurnDetector,
        previous_topic=resumed_state.current_topic,
        endpoint_context=EndpointContext(
            current_topic=resumed_state.current_topic,
            current_goal=(
                resumed_state.current_goal.name if resumed_state.current_goal else None
            ),
            current_intent=resumed_state.user_intent,
            pending_action=(
                resumed_state.pending_action.model_dump(mode="json")
                if resumed_state.pending_action
                else None
            ),
            missing_slots=(
                (resumed_state.pending_action.missing,)
                if resumed_state.pending_action
                and resumed_state.pending_action.missing
                else ()
            ),
        ),
    )

    await websocket.send_json(
        {
            "type": "session_started",
            "session_id": str(session_id),
            "state": "live",
            "voice_protocol": VOICE_PROTOCOL_VERSION,
            "audio": {
                "encoding": "pcm_s16le",
                "sample_rate": PCM_SAMPLE_RATE,
                "channels": PCM_CHANNELS,
                "frame_ms": 40,
                "sequence_required": True,
            },
            "turn_detection": {
                "authority": "server",
                "provider": turn_detector.speech_provider.name,
                "vad": turn_detector.diagnostics(),
                "semantic_endpointing": True,
                "semantic_provider": turn_detector.semantic.classifier.name,
                "semantic_fallback_active": (
                    turn_detector.semantic.classifier.fallback_active
                ),
                "endpointing": {
                    "provider": turn_detector.semantic.classifier.name,
                    "model": getattr(
                        turn_detector.semantic.classifier,
                        "model_name",
                        settings.semantic_endpointing_model,
                    ),
                    "version": turn_detector.semantic.model_version,
                    "source": getattr(
                        turn_detector.semantic.classifier, "model_source", "internal_hybrid"
                    ),
                    "size": getattr(
                        turn_detector.semantic.classifier, "model_size", "small-local-hybrid"
                    ),
                    "device": settings.semantic_endpointing_model_device,
                    "supported_languages": _supported_endpoint_languages(),
                    "inference_timeout_seconds": (
                        settings.semantic_endpointing_inference_timeout_seconds
                    ),
                    "warm_start_ms": getattr(
                        turn_detector.semantic.classifier, "warm_start_ms", None
                    ),
                    "cold_start_ms": getattr(
                        turn_detector.semantic.classifier, "cold_start_ms", None
                    ),
                    "latency_summary": getattr(
                        turn_detector.semantic.classifier, "latency_summary", lambda: {}
                    )(),
                    "production_fallback_policy": (
                        settings.semantic_endpointing_production_fallback_policy
                    ),
                    "fallback_active": (
                        turn_detector.semantic.classifier.fallback_active
                    ),
                    "fallback_mode": settings.semantic_endpointing_fallback_mode,
                },
            },
            "topic_classifier": _topic_classifier_diagnostics(settings),
        }
    )
    await _send_state(websocket, "listening")
    log.info(
        "live_voice session_started user=%s email=%s session=%s",
        user.id,
        user.email,
        session_id,
    )

    stt: StreamingSTT | None = None
    audio_ingress = VoiceAudioIngress(max_utterance_ms=None)
    audio_ingress.start("stream")
    cancel_registry = TurnCancellationRegistry()
    inflight_tasks: set[asyncio.Task] = set()
    preload_tasks: dict[str, asyncio.Task] = {}
    active_voice_turn_id: str | None = None
    playback_turn_id: str | None = None
    barge_in_pending_frames = 0
    endpoint_sequence = 0

    def _playback_started(turn_id: str) -> None:
        nonlocal playback_turn_id
        playback_turn_id = turn_id

    def _turn_task_done(task: asyncio.Task) -> None:
        inflight_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            log.error(
                "live_voice_background_turn_failed: %s",
                error,
                exc_info=(type(error), error, error.__traceback__),
            )

    def _cancel_background_turns() -> int:
        cancelled = 0
        for task in list(inflight_tasks):
            if not task.done():
                task.cancel()
                cancelled += 1
        return cancelled

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if msg_type == "end":
                break
            if msg_type == "playback_complete":
                completed_turn = str(msg.get("turn_id") or "")
                if not completed_turn or completed_turn == playback_turn_id:
                    playback_turn_id = None
                continue

            if msg_type == "interrupt":
                barge_in_pending_frames = 50
                turn_id = msg.get("turn_id") or ""
                if turn_id in {"", "all", "*"}:
                    cancelled_count = (
                        cancel_registry.cancel_all() + _cancel_background_turns()
                    )
                    playback_turn_id = None
                    if cancelled_count:
                        await mark_interrupted(
                            str(user.id), str(session_id), turn_id=None
                        )
                        await websocket.send_json(
                            {
                                "type": "turn_cancelled",
                                "turn_id": "all",
                                "cancelled_count": cancelled_count,
                            }
                        )
                        await _send_state(websocket, "listening")
                    continue
                cancelled = cancel_registry.cancel(turn_id)
                background_cancelled = _cancel_background_turns()
                if turn_id == playback_turn_id:
                    playback_turn_id = None
                await mark_interrupted(str(user.id), str(session_id), turn_id=turn_id)
                await websocket.send_json(
                    {
                        "type": "turn_cancelled",
                        "turn_id": turn_id,
                        "backend_cancelled": cancelled or background_cancelled > 0,
                    }
                )
                await _send_state(websocket, "listening")
                continue

            if msg_type == "audio_route_changed":
                # Capture routes can change gain/frame timing abruptly. Drop any
                # partial acoustic/STT state so it cannot bleed across devices.
                route_turn_id = active_voice_turn_id
                turn_detector.cancel()
                if route_turn_id is not None:
                    preload_task = preload_tasks.pop(route_turn_id, None)
                    if preload_task is not None:
                        preload_task.cancel()
                    await websocket.send_json(
                        {
                            "type": "turn_cancelled",
                            "turn_id": route_turn_id,
                            "reason": "audio_route_changed",
                        }
                    )
                active_voice_turn_id = None
                stt = None
                audio_ingress.start("stream")
                await websocket.send_json(
                    {
                        "type": "audio_route_reset",
                        "route": msg.get("route") or "unknown",
                        "acoustic_state": "silence",
                    }
                )
                await _send_state(websocket, "listening")
                continue

            if not settings.live_voice_v2:
                if msg_type == "text_turn":
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    await _send_state(websocket, "thinking")
                    turn_id = msg.get("turn_id") or str(uuid.uuid4())
                    await _run_turn_pipeline(
                        websocket,
                        user,
                        session_id,
                        turn_id,
                        text,
                        cancel_registry,
                        on_playback_started=_playback_started,
                    )
                elif msg_type == "audio_chunk":
                    await websocket.send_json(
                        {
                            "type": "transcript_partial",
                            "text": "",
                            "note": "Enable LIVE_VOICE_V2 for streaming STT",
                        }
                    )
                continue

            if msg_type == "audio_frame":
                if not audio_format_is_supported(msg):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": msg.get("turn_id"),
                            "code": "unsupported_audio_format",
                            "message": "Live voice requires 16 kHz mono PCM16 audio.",
                        }
                    )
                    continue
                data_b64 = msg.get("data") or ""
                try:
                    pcm = base64.b64decode(data_b64, validate=True)
                except Exception:
                    continue
                turn_id = msg.get("turn_id") or ""
                raw_sequence = msg.get("sequence")
                try:
                    sequence = int(raw_sequence) if raw_sequence is not None else None
                except (TypeError, ValueError):
                    continue
                raw_timestamp = msg.get("timestamp_ms")
                try:
                    timestamp_ms = (
                        int(raw_timestamp) if raw_timestamp is not None else None
                    )
                except (TypeError, ValueError):
                    continue
                acceptance = audio_ingress.accept(
                    turn_id=turn_id,
                    sequence=sequence,
                    pcm=pcm,
                    timestamp_ms=timestamp_ms,
                )
                if not acceptance.accepted:
                    if acceptance.reason in {"utterance_too_large", "frame_too_large"}:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "turn_id": turn_id,
                                "code": "utterance_too_large",
                                "message": "Voice segment exceeded the maximum buffered duration.",
                            }
                        )
                    continue
                if turn_id != "stream":
                    if stt is None:
                        continue
                    partial = await stt.feed_audio(pcm)
                    if partial:
                        hypothesis = (
                            partial
                            if isinstance(partial, STTPartial)
                            else STTPartial(text=str(partial), language="unknown")
                        )
                        await websocket.send_json(
                            {
                                "type": "transcript_partial",
                                "turn_id": turn_id,
                                "text": hypothesis.text,
                                "confidence": hypothesis.confidence,
                                "language": _safe_language(hypothesis.language),
                                "language_confidence": hypothesis.language_confidence,
                                "languages": _safe_languages(hypothesis.languages),
                                "language_changed": hypothesis.language_changed,
                                "code_switching_detected": hypothesis.code_switching_detected,
                                "sequence": hypothesis.sequence,
                                "stability": hypothesis.stability,
                                "audio_ms": hypothesis.audio_ms,
                                "is_final": False,
                            }
                        )
                    continue

                ai_speaking = (
                    playback_turn_id is not None
                    or cancel_registry.has_active
                    or any(not task.done() for task in inflight_tasks)
                    or barge_in_pending_frames > 0
                )
                if barge_in_pending_frames > 0:
                    barge_in_pending_frames -= 1
                was_active = turn_detector.active
                detection_events = await asyncio.to_thread(
                    turn_detector.process,
                    pcm,
                    ai_speaking=ai_speaking,
                )
                started = next(
                    (
                        event
                        for event in detection_events
                        if event.signal == TurnSignal.SPEECH_STARTED
                    ),
                    None,
                )
                if started is not None:
                    audio_ingress.take_metrics()  # discard idle-stream counters
                    active_voice_turn_id = str(uuid.uuid4())
                    endpoint_sequence = 0
                    stt = get_streaming_stt(settings)
                    await stt.on_speech_start()
                    interrupted_turn_id = playback_turn_id
                    cancelled_count = (
                        cancel_registry.cancel_all() + _cancel_background_turns()
                    )
                    if ai_speaking:
                        await mark_interrupted(
                            str(user.id),
                            str(session_id),
                            turn_id=interrupted_turn_id,
                        )
                        if interrupted_turn_id is not None:
                            await websocket.send_json(
                                {
                                    "type": "turn_cancelled",
                                    "turn_id": interrupted_turn_id,
                                    "backend_cancelled": cancelled_count > 0,
                                }
                            )
                        elif cancelled_count:
                            await websocket.send_json(
                                {
                                    "type": "turn_cancelled",
                                    "turn_id": "all",
                                    "cancelled_count": cancelled_count,
                                }
                            )
                    playback_turn_id = None
                    barge_in_pending_frames = 0
                    await mark_user_speaking(
                        str(user.id),
                        str(session_id),
                        turn_id=active_voice_turn_id,
                    )
                    preload_tasks[active_voice_turn_id] = asyncio.create_task(
                        _preload_context_for_turn(
                            user,
                            session_id,
                            active_voice_turn_id,
                            time.monotonic(),
                        )
                    )
                    await websocket.send_json(
                        {
                            "type": "speech_detected",
                            "turn_id": active_voice_turn_id,
                            "speech_probability": started.speech_probability,
                            "vad_provider": turn_detector.speech_provider.name,
                            "pause_kind": (
                                started.pause_kind.value if started.pause_kind else None
                            ),
                            "acoustic": (
                                started.acoustic_decision.to_transport()
                                if started.acoustic_decision
                                else None
                            ),
                            "preroll_ms": len(started.preroll_pcm)
                            * 1_000
                            // (PCM_SAMPLE_RATE * 2),
                        }
                    )
                    await _send_state(websocket, "user_speaking")
                    partial = await stt.feed_audio(started.preroll_pcm)
                elif was_active and stt is not None:
                    partial = await stt.feed_audio(pcm)
                else:
                    partial = None

                if partial:
                    hypothesis = (
                        partial
                        if isinstance(partial, STTPartial)
                        else STTPartial(text=str(partial), language="unknown")
                    )
                    await websocket.send_json(
                        {
                            "type": "transcript_partial",
                            "turn_id": active_voice_turn_id,
                            "text": hypothesis.text,
                            "confidence": hypothesis.confidence,
                            "language": _safe_language(hypothesis.language),
                            "language_confidence": hypothesis.language_confidence,
                            "languages": _safe_languages(hypothesis.languages),
                            "language_changed": hypothesis.language_changed,
                            "code_switching_detected": hypothesis.code_switching_detected,
                            "sequence": hypothesis.sequence,
                            "stability": hypothesis.stability,
                            "audio_ms": hypothesis.audio_ms,
                            "is_final": False,
                        }
                    )
                    turn_detector.update_transcript(
                        hypothesis.text,
                        confidence=hypothesis.confidence,
                        stability=hypothesis.stability,
                        language=hypothesis.language,
                        language_confidence=hypothesis.language_confidence,
                        languages=hypothesis.languages,
                        code_switching_detected=hypothesis.code_switching_detected,
                        partial_sequence=hypothesis.sequence,
                    )

                for detection in detection_events:
                    if detection.signal == TurnSignal.SPEECH_STARTED:
                        continue
                    if detection.signal in {
                        TurnSignal.THINKING_PAUSE,
                        TurnSignal.SPEECH_RESUMED,
                    }:
                        await websocket.send_json(
                            {
                                "type": detection.signal.value,
                                "turn_id": active_voice_turn_id,
                                "speech_probability": detection.speech_probability,
                                "silence_ms": detection.silence_ms,
                                "completion_probability": detection.completion_probability,
                                "pause_kind": (
                                    detection.pause_kind.value
                                    if detection.pause_kind
                                    else None
                                ),
                                "endpointing": (
                                    detection.endpoint_decision.to_transport()
                                    if detection.endpoint_decision
                                    else None
                                ),
                                "acoustic": (
                                    detection.acoustic_decision.to_transport()
                                    if detection.acoustic_decision
                                    else None
                                ),
                            }
                        )
                        if detection.signal == TurnSignal.THINKING_PAUSE:
                            await _send_state(websocket, "user_speaking")
                    if detection.signal == TurnSignal.ENDPOINT:
                        completed_turn_id = active_voice_turn_id
                        completed_stt = stt
                        active_voice_turn_id = None
                        stt = None
                        if completed_turn_id is None or completed_stt is None:
                            continue
                        await websocket.send_json(
                            {
                                "type": "endpoint_detected",
                                "turn_id": completed_turn_id,
                                "reason": detection.reason,
                                "silence_ms": detection.silence_ms,
                                "completion_probability": detection.completion_probability,
                                "pause_kind": (
                                    detection.pause_kind.value
                                    if detection.pause_kind
                                    else None
                                ),
                                "endpointing": (
                                    detection.endpoint_decision.to_transport()
                                    if detection.endpoint_decision
                                    else None
                                ),
                                "acoustic": (
                                    detection.acoustic_decision.to_transport()
                                    if detection.acoustic_decision
                                    else None
                                ),
                                "endpoint_sequence": endpoint_sequence + 1,
                            }
                        )
                        endpoint_sequence += 1
                        await _send_state(websocket, "thinking")
                        finalizer = asyncio.create_task(
                            _finalize_detected_turn(
                                websocket,
                                user,
                                session_id,
                                completed_turn_id,
                                completed_stt,
                                cancel_registry,
                                detection=detection,
                                transport_metrics=audio_ingress.take_metrics(),
                                preload_task=preload_tasks.pop(completed_turn_id, None),
                                on_playback_started=_playback_started,
                            )
                        )
                        inflight_tasks.add(finalizer)
                        finalizer.add_done_callback(_turn_task_done)
                continue

            if msg_type in {"speech_start", "speech_end"}:
                await websocket.send_json(
                    {
                        "type": "error",
                        "turn_id": msg.get("turn_id"),
                        "code": "client_turn_boundary_unsupported",
                        "message": (
                            "Voice protocol 4.0 uses continuous audio_frame "
                            "messages and server-authoritative turn detection."
                        ),
                    }
                )
                continue

            if msg_type == "speech_start":
                turn_id = msg.get("turn_id") or str(uuid.uuid4())
                turn_detector.cancel()
                if not audio_format_is_supported(msg):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": turn_id,
                            "code": "unsupported_audio_format",
                            "message": "Live voice requires 16 kHz mono PCM16 audio.",
                        }
                    )
                    continue
                cancelled_count = cancel_registry.cancel_all()
                if cancelled_count:
                    await mark_interrupted(str(user.id), str(session_id), turn_id=None)
                    await websocket.send_json(
                        {
                            "type": "turn_cancelled",
                            "turn_id": "all",
                            "cancelled_count": cancelled_count,
                        }
                    )
                stt = get_streaming_stt(settings)
                await stt.on_speech_start()
                audio_ingress.start(turn_id)
                await mark_user_speaking(str(user.id), str(session_id), turn_id=turn_id)
                preload_tasks[turn_id] = asyncio.create_task(
                    _preload_context_for_turn(
                        user, session_id, turn_id, time.monotonic()
                    )
                )
                log.info(
                    "live_voice speech_start user=%s session=%s turn=%s cancelled=%d",
                    user.id,
                    session_id,
                    turn_id,
                    cancelled_count,
                )
                continue

            turn_id = msg.get("turn_id") or str(uuid.uuid4())

            if msg_type == "speech_end":
                if not _rate_limiter.allow(str(user.id)):
                    audio_ingress.cancel()
                    if stt:
                        stt.reset()
                    stt = None
                    audio_ingress.start("stream")
                    preload_task = preload_tasks.pop(turn_id, None)
                    if preload_task:
                        preload_task.cancel()
                    await mark_listening(str(user.id), str(session_id))
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": turn_id,
                            "message": "Rate limit exceeded; try again shortly.",
                        }
                    )
                    continue

                stt_t0 = time.monotonic()
                transcript = ""
                final_result = STTFinal(text="")
                stt_metrics: dict[str, Any] = {}
                if stt:
                    raw_final = await stt.on_speech_end()
                    stt_metrics = stt.consume_metrics()
                    final_result = (
                        raw_final
                        if isinstance(raw_final, STTFinal)
                        else STTFinal(
                            text=str(raw_final or ""),
                            confidence=float(stt_metrics.get("stt_confidence", 0.0)),
                            language=_safe_language(stt_metrics.get("stt_language")),
                            language_confidence=float(
                                stt_metrics.get("stt_language_confidence", 0.0) or 0.0
                            ),
                            languages=_safe_languages(stt_metrics.get("stt_languages")),
                            code_switching_detected=bool(
                                stt_metrics.get("stt_code_switching_detected", False)
                            ),
                        )
                    )
                    transcript = final_result.text
                stt_metrics.update(audio_ingress.finish(turn_id))
                audio_ingress.start("stream")
                stt = None
                stt_metrics.setdefault("stt_confidence", final_result.confidence)
                stt_metrics.setdefault("stt_language", _safe_language(final_result.language))
                stt_metrics.setdefault(
                    "stt_language_confidence", final_result.language_confidence
                )
                final_audio_ms = final_result.audio_ms or int(
                    stt_metrics.get("audio_ms", 0)
                )
                stt_final_ms = int((time.monotonic() - stt_t0) * 1000)
                transcript = (transcript or "").strip()
                log.info(
                    "live_voice speech_end user=%s session=%s turn=%s stt_final_ms=%d transcript_len=%d empty=%s",
                    user.id,
                    session_id,
                    turn_id,
                    stt_final_ms,
                    len(transcript),
                    not transcript,
                )

                if not transcript:
                    preload_task = preload_tasks.pop(turn_id, None)
                    if preload_task:
                        preload_task.cancel()
                    await websocket.send_json(
                        {
                            "type": "transcript_final",
                            "turn_id": turn_id,
                            "text": "",
                            "confidence": final_result.confidence,
                            "language": _safe_language(final_result.language),
                            "language_confidence": final_result.language_confidence,
                            "languages": _safe_languages(final_result.languages),
                            "language_changed": final_result.language_changed,
                            "code_switching_detected": final_result.code_switching_detected,
                            "sequence": final_result.sequence,
                            "audio_ms": final_audio_ms,
                            "no_speech_probability": final_result.no_speech_probability,
                            "is_final": True,
                        }
                    )
                    await mark_listening(str(user.id), str(session_id))
                    await _send_state(websocket, "listening")
                    continue

                log.info(
                    "live_voice transcript user=%s session=%s turn=%s text=%r",
                    user.id,
                    session_id,
                    turn_id,
                    transcript[:200],
                )
                await websocket.send_json(
                    {
                        "type": "transcript_final",
                        "turn_id": turn_id,
                        "text": transcript,
                        "confidence": final_result.confidence,
                        "language": _safe_language(final_result.language),
                        "language_confidence": final_result.language_confidence,
                        "languages": _safe_languages(final_result.languages),
                        "language_changed": final_result.language_changed,
                        "code_switching_detected": final_result.code_switching_detected,
                        "sequence": final_result.sequence,
                        "audio_ms": final_audio_ms,
                        "no_speech_probability": final_result.no_speech_probability,
                        "is_final": True,
                    }
                )
                await _send_state(websocket, "thinking")
                await _send_state(websocket, "speaking")
                task = asyncio.create_task(
                    _run_turn_pipeline(
                        websocket,
                        user,
                        session_id,
                        turn_id,
                        transcript,
                        cancel_registry,
                        stt_final_ms=stt_final_ms,
                        stt_metrics=stt_metrics,
                        preload_task=preload_tasks.pop(turn_id, None),
                        on_playback_started=_playback_started,
                    )
                )
                inflight_tasks.add(task)
                task.add_done_callback(_turn_task_done)
                continue

            if msg_type == "text_turn":
                text = (msg.get("text") or "").strip()
                if not text:
                    continue
                if not _rate_limiter.allow(str(user.id)):
                    await websocket.send_json(
                        {
                            "type": "error",
                            "turn_id": turn_id,
                            "message": "Rate limit exceeded; try again shortly.",
                        }
                    )
                    continue
                await _send_state(websocket, "thinking")
                await _send_state(websocket, "speaking")
                task = asyncio.create_task(
                    _run_turn_pipeline(
                        websocket,
                        user,
                        session_id,
                        turn_id,
                        text,
                        cancel_registry,
                        on_playback_started=_playback_started,
                    )
                )
                inflight_tasks.add(task)
                task.add_done_callback(_turn_task_done)

    except WebSocketDisconnect:
        log.info("live_voice disconnected user=%s session=%s", user.id, session_id)
    finally:
        turn_detector.cancel()
        audio_ingress.cancel()
        if stt is not None:
            stt.reset()
        cancel_registry.cancel_all()
        for task in list(inflight_tasks):
            task.cancel()
        for task in list(preload_tasks.values()):
            task.cancel()
        if inflight_tasks:
            await asyncio.gather(*inflight_tasks, return_exceptions=True)
        if preload_tasks:
            await asyncio.gather(*preload_tasks.values(), return_exceptions=True)
        async with async_session() as db:
            result = await db.execute(
                select(LiveSession).where(LiveSession.id == session_id)
            )
            live = result.scalar_one_or_none()
            if live:
                live.state = "ended"
                live.ended_at = datetime.now(UTC)
                await db.commit()
            await conversation_state_manager.end(
                db,
                user_id=user.id,
                conversation_id=session_id,
            )
        try:
            await websocket.send_json({"type": "session_ended", "state": "resting"})
        except Exception:
            pass
