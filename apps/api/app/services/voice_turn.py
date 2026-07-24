"""Live Voice v2 streaming turn pipeline."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..conversation.contracts import InputModality
from ..conversation.service import stream_conversation
from ..services.companion_orchestrator import preload_turn_context

log = logging.getLogger("aipal.voice_turn")


def _session_uuid(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(session_id)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, f"aipal:voice-session:{session_id}")


async def run_voice_turn_stream(
    db: AsyncSession,
    user: User,
    text: str,
    session_id: str,
    *,
    turn_id: str | None = None,
    stt_metadata: dict[str, Any] | None = None,
    cancel_event: asyncio.Event | None = None,
    preloaded_context: dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield streaming Brain events for live voice."""
    t0 = time.monotonic()
    sid = session_id or str(uuid.uuid4())

    async for canonical_event in stream_conversation(
        db,
        user,
        text,
        conversation_id=_session_uuid(sid),
        modality=InputModality.LIVE_VOICE,
        turn_id=turn_id,
        source_context={"stt": stt_metadata or {}},
        cancel_event=cancel_event,
        preloaded_context=preloaded_context,
    ):
        event = canonical_event.to_transport()
        if cancel_event and cancel_event.is_set():
            return
        metrics = dict(event.get("metrics") or {})
        if event.get("type") == "reply_delta" and "first_token_ms" in metrics:
            metrics.setdefault("first_reply_delta_ms", metrics["first_token_ms"])
        if event.get("type") == "turn_complete":
            metrics["turn_total_ms"] = int((time.monotonic() - t0) * 1000)
        yield {**event, "metrics": metrics}


async def preload_voice_context(
    db: AsyncSession,
    user: User,
    session_id: str,
    *,
    partial_message: str = "",
    speech_start_started_at: float | None = None,
) -> dict[str, Any]:
    started = speech_start_started_at or time.monotonic()
    payload = await preload_turn_context(
        db,
        user,
        conversation_id=_session_uuid(session_id),
        partial_message=partial_message,
    )
    payload["speech_start_to_context_ready_ms"] = int(
        (time.monotonic() - started) * 1000
    )
    return payload
