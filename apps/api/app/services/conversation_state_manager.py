"""Compatibility facade over the one durable conversation state manager."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from ..conversation.state import (
    ConversationState,
    ConversationStatePatch,
    ConversationStatus,
    InterruptionState,
    PendingAction,
    Speaker,
    conversation_state_manager,
)
from ..db import async_session


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _legacy_payload(state: ConversationState) -> dict[str, Any]:
    payload = state.model_dump(mode="json")
    payload["last_state"] = state.status.value
    payload["current_intent"] = state.user_intent
    payload["interrupted_turn_id"] = state.last_interruption.turn_id if state.last_interruption else None
    return payload


async def get_voice_session_state(user_id: str, session_id: str) -> dict[str, Any]:
    async with async_session() as db:
        state = await conversation_state_manager.load(
            db,
            user_id=_uuid(user_id),
            conversation_id=_uuid(session_id),
            create=True,
        )
    assert state is not None
    return _legacy_payload(state)


async def update_voice_session_state(user_id: str, session_id: str, **updates: Any) -> dict[str, Any]:
    user_uuid = _uuid(user_id)
    conversation_uuid = _uuid(session_id)
    async with async_session() as db:
        current = await conversation_state_manager.load(
            db,
            user_id=user_uuid,
            conversation_id=conversation_uuid,
            create=True,
            use_cache=False,
        )
        assert current is not None
        patch_values: dict[str, Any] = {}
        metadata = dict(current.metadata)

        mapping = {
            "current_intent": "user_intent",
            "last_state": "status",
        }
        direct_fields = set(ConversationStatePatch.model_fields)
        for key, value in updates.items():
            target = mapping.get(key, key)
            if target == "pending_action":
                if isinstance(value, dict):
                    pending_payload = dict(value)
                    awaiting_confirmation = pending_payload.get("state") == "awaiting_confirmation"
                    pending_payload.setdefault("requires_confirmation", awaiting_confirmation)
                    patch_values[target] = PendingAction.model_validate(pending_payload)
                    if awaiting_confirmation:
                        patch_values["pending_confirmation"] = {
                            "prompt": str(updates.get("confirmation_prompt") or "Please confirm."),
                        }
                else:
                    patch_values[target] = value
                if value is None:
                    patch_values["pending_confirmation"] = None
            elif target == "interrupted_turn_id":
                patch_values["last_interruption"] = (
                    InterruptionState(turn_id=str(value)) if value is not None else None
                )
            elif target in direct_fields:
                patch_values[target] = value
            elif target != "conversation_id":
                metadata[target] = value
        if metadata != current.metadata:
            patch_values["metadata"] = metadata

        state = await conversation_state_manager.patch(
            db,
            user_id=user_uuid,
            conversation_id=conversation_uuid,
            patch=ConversationStatePatch.model_validate(patch_values),
        )
    return _legacy_payload(state)


async def mark_user_speaking(user_id: str, session_id: str, *, turn_id: str | None = None) -> dict[str, Any]:
    return await update_voice_session_state(
        user_id,
        session_id,
        status=ConversationStatus.USER_SPEAKING,
        last_speaker=Speaker.USER,
        currently_speaking=Speaker.USER,
        current_turn_id=turn_id,
        speech_started_at=datetime.now(UTC).isoformat(),
    )


async def mark_ai_speaking(user_id: str, session_id: str, *, turn_id: str | None = None) -> dict[str, Any]:
    return await update_voice_session_state(
        user_id,
        session_id,
        status=ConversationStatus.AI_SPEAKING,
        last_speaker=Speaker.AIPAL,
        currently_speaking=Speaker.AIPAL,
        current_turn_id=turn_id,
    )


async def mark_listening(user_id: str, session_id: str) -> dict[str, Any]:
    return await update_voice_session_state(
        user_id,
        session_id,
        status=ConversationStatus.LISTENING,
        currently_speaking=Speaker.NONE,
        current_turn_id=None,
        partial_transcript=None,
        partial_confidence=None,
    )


async def mark_interrupted(
    user_id: str,
    session_id: str,
    *,
    turn_id: str | None,
) -> dict[str, Any]:
    async with async_session() as db:
        state = await conversation_state_manager.record_interruption(
            db,
            user_id=_uuid(user_id),
            conversation_id=_uuid(session_id),
            turn_id=turn_id,
        )
    return _legacy_payload(state)


async def end_voice_session(user_id: str, session_id: str) -> dict[str, Any]:
    async with async_session() as db:
        state = await conversation_state_manager.end(
            db,
            user_id=_uuid(user_id),
            conversation_id=_uuid(session_id),
        )
    return _legacy_payload(state)
