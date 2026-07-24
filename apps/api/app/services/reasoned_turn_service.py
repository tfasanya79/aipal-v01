"""Phase 7 reason -> validate -> execute -> final-answer conversation loop."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..conversation.reasoning import ReasoningToolCall
from ..config import get_settings
from ..models import Conversation, Message, User
from . import companion_response_service as response_service
from . import conversation as conversation_service
from . import plan_draft as draft_service
from .ai_reasoning_engine import (
    ReasoningContractError,
    generate_reasoned_final_response,
    reason_about_turn,
    stream_reasoned_final_response,
)
from .memory_manager import memory_manager
from .proactive_conversation_service import get_or_create_preferences
from .reasoning_policy import ReasoningValidation, validate_reasoning_decision
from .streaming_response import SpeechSegmenter
from .tool_registry import ToolExecutionContext, tool_registry

log = logging.getLogger("aipal.reasoned_turn")
EventSink = Callable[[dict[str, Any]], Awaitable[None]]
llm_chat_stream = response_service.conversation_llm_stream


@dataclass(slots=True)
class ReasonedTurnAttempt:
    result: dict[str, Any] | None
    fallback_reason: str | None = None


def _raise_if_cancelled(cancel_event: asyncio.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise asyncio.CancelledError


def _title(message: str) -> str:
    words = message.split()
    return (" ".join(words[:5]) or "Companion")[:60].title()


async def _conversation(
    db: AsyncSession,
    user: User,
    conversation_id: uuid.UUID | None,
    message: str,
) -> Conversation:
    if conversation_id is not None:
        row = (
            await db.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
    row = Conversation(
        id=conversation_id or uuid.uuid4(),
        user_id=user.id,
        mode="companion",
        title=_title(message),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def _context_items(memory: dict[str, Any]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for key in ("goals", "projects", "people", "tasks", "memories"):
        for item in memory.get(key, []):
            source = str(item.get("source_type") or key.rstrip("s"))
            text = " ".join(
                str(item.get(field) or "").strip()
                for field in ("title", "name", "content", "description")
                if item.get(field)
            ).strip()
            if text:
                selected.append(
                    {
                        "id": item.get("id"),
                        "source": source,
                        "text": text[:320],
                        "life_area": item.get("life_area"),
                    }
                )
            if len(selected) >= 10:
                return selected
    return selected


def _history(stable: dict[str, Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for item in stable.get("recent_discussions", [])[-6:]:
        history.append(
            {
                "role": str(item.get("role") or "user"),
                "content": str(item.get("content") or "")[:600],
            }
        )
    return history


def _preferences(row: Any, stable: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_summary": stable.get("profile_summary") or "",
        "tone": row.tone,
        "humor_level": row.humor_level,
        "directness_level": row.directness_level,
        "response_length": row.response_length,
        "voice_pace": row.voice_pace,
        "voice_profile": row.tts_voice,
        "tts_voice": row.tts_voice,
    }


async def _execute_call(
    db: AsyncSession,
    user: User,
    message: str,
    call: ReasoningToolCall,
    source: str,
) -> dict[str, Any]:
    result = await tool_registry.execute(
        ToolExecutionContext(
            db=db,
            user=user,
            message=message,
            source=source,
            source_context={"tool": call.name, **call.arguments},
            call_id=call.call_id,
        ),
        call.name,
        call.arguments,
    )
    payload = result.public_payload()
    return {
        "call_id": call.call_id,
        "tool": call.name,
        "status": "completed",
        "tool_action": payload.get("tool_action"),
        "tool_result": payload.get("tool_result"),
        "requires_confirmation": bool(payload.get("requires_confirmation")),
        "confirmation_prompt": payload.get("confirmation_prompt"),
        "plan_draft": payload.get("plan_draft"),
        "fallback_reply": payload.get("reply"),
    }


def _pending_after_execution(
    validation: ReasoningValidation,
    tool_results: list[dict[str, Any]],
) -> ReasoningToolCall | None:
    if validation.pending_call is not None:
        return validation.pending_call
    for result in tool_results:
        if result.get("requires_confirmation") and result.get("plan_draft"):
            return ReasoningToolCall(
                call_id=f"apply_{result['call_id']}",
                name="planner_engine",
                arguments={"action": "confirm_draft"},
                rationale="Apply the validated planner draft after user confirmation.",
                requires_confirmation=True,
            )
    return None


def _fallback_final(
    *,
    missing: list[str],
    confirmation: str | None,
    tool_results: list[dict[str, Any]],
) -> str:
    if confirmation:
        return confirmation
    if missing:
        return missing[0]
    for result in reversed(tool_results):
        if result.get("fallback_reply"):
            return str(result["fallback_reply"])
    return "I’m with you. Tell me a little more about what you want to do next."


async def try_run_reasoned_turn(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None,
    source: str,
    source_context: dict[str, Any] | None,
    preloaded_context: dict[str, Any] | None,
    cancel_event: asyncio.Event | None,
    event_sink: EventSink | None = None,
) -> ReasonedTurnAttempt:
    turn_started = time.perf_counter()
    _raise_if_cancelled(cancel_event)
    conversation = await _conversation(db, user, conversation_id, message)
    stable = dict((preloaded_context or {}).get("_stable_memory") or {})
    if not stable:
        stable = await memory_manager.retrieve_stable(
            db, user, conversation_id=conversation.id
        )
    query = await memory_manager.retrieve_query(db, user.id, message, limit=16)
    merged = memory_manager.merge(stable, query)
    preferences_row = await get_or_create_preferences(db, user.id)
    context_items = _context_items(merged)
    history = _history(stable)
    preferences = _preferences(preferences_row, stable)
    conversation_state = dict((source_context or {}).get("conversation_state") or {})
    if event_sink is not None:
        await event_sink(
            {
                "type": "context_ready",
                "mode": str(conversation_state.get("conversation_mode") or "companion"),
                "emotion": dict(conversation_state.get("current_emotion") or {}),
                "metrics": merged.get("metrics", {}),
                "stages": ["stable", "query_specific"],
                "voice_profile": preferences.get("voice_profile") or "calm_female",
            }
        )

    try:
        outcome = await reason_about_turn(
            user_message=message,
            output_channel=source,
            context_items=context_items,
            conversation_history=history,
            user_preferences=preferences,
            conversation_state=conversation_state,
            llm=response_service.llm_chat,
        )
    except (ReasoningContractError, RuntimeError, ValueError) as exc:
        reason = type(exc).__name__
        log.warning("reasoning_compatibility_fallback reason=%s", reason)
        return ReasonedTurnAttempt(result=None, fallback_reason=reason)

    _raise_if_cancelled(cancel_event)
    validation = validate_reasoning_decision(
        outcome.decision,
        conversation_state=conversation_state,
    )
    outcome.metrics.validation_ms = validation.validation_ms
    log.info(
        "reasoning_validated intent=%s tools=%s pending_resolution=%s errors=%d",
        outcome.decision.primary_intent,
        [call.name for call in outcome.decision.tool_calls],
        outcome.decision.pending_action_resolution.value,
        len(validation.errors),
    )
    if event_sink is not None:
        await event_sink(
            {
                "type": "reasoning_complete",
                "intent": outcome.decision.primary_intent,
                "mode": outcome.decision.mode.value,
                "metrics": {
                    "reasoning_ms": outcome.metrics.reasoning_ms,
                    "validation_ms": validation.validation_ms,
                },
            }
        )
    if validation.discarded_call and validation.discarded_call.name == "planner_engine":
        await draft_service.clear_draft(db, user.id)

    tool_results: list[dict[str, Any]] = []
    completed_ids: set[str] = set()
    for call in validation.executable_calls:
        _raise_if_cancelled(cancel_event)
        if any(dependency not in completed_ids for dependency in call.depends_on):
            validation.errors.append(f"Unmet dependency for {call.call_id}")
            break
        started = time.perf_counter()
        try:
            if event_sink is not None:
                await event_sink(
                    {"type": "tool_started", "tool": call.name, "call_id": call.call_id}
                )
            result = await _execute_call(db, user, message, call, source)
            duration_ms = int((time.perf_counter() - started) * 1_000)
            result["duration_ms"] = duration_ms
            outcome.metrics.tool_execution_ms += duration_ms
            tool_results.append(result)
            completed_ids.add(call.call_id)
            if event_sink is not None:
                await event_sink(
                    {
                        "type": "tool_completed",
                        "tool": call.name,
                        "call_id": call.call_id,
                        "status": "completed",
                        "duration_ms": duration_ms,
                    }
                )
        except Exception as exc:
            log.exception("reasoning_tool_failed tool=%s", call.name)
            validation.errors.append(f"{call.name} failed: {type(exc).__name__}")
            tool_results.append(
                {"call_id": call.call_id, "tool": call.name, "status": "failed"}
            )
            if event_sink is not None:
                await event_sink(
                    {
                        "type": "tool_completed",
                        "tool": call.name,
                        "call_id": call.call_id,
                        "status": "failed",
                    }
                )
            break

    pending_call = _pending_after_execution(validation, tool_results)
    requires_confirmation = pending_call is not None
    confirmation_message = None
    if requires_confirmation:
        confirmation_message = (
            outcome.decision.confirmation_message
            or next(
                (
                    str(result.get("confirmation_prompt"))
                    for result in tool_results
                    if result.get("confirmation_prompt")
                ),
                None,
            )
            or "Would you like me to continue with that action?"
        )

    _raise_if_cancelled(cancel_event)
    if event_sink is None:
        try:
            reply, final_ms = await generate_reasoned_final_response(
                user_message=message,
                output_channel=source,
                decision=outcome.decision,
                tool_results=tool_results,
                context_items=context_items,
                conversation_history=history,
                user_preferences=preferences,
                confirmation_required=requires_confirmation,
                confirmation_message=confirmation_message,
                validation_errors=validation.errors,
                llm=response_service.llm_chat,
            )
            outcome.metrics.final_response_ms = final_ms
        except (ReasoningContractError, RuntimeError, ValueError):
            log.exception("reasoning_final_response_fallback")
            reply = _fallback_final(
                missing=outcome.decision.missing_information,
                confirmation=confirmation_message,
                tool_results=tool_results,
            )
    else:
        response_started = time.perf_counter()
        parts: list[str] = []
        stream_settings = get_settings()
        segmenter = SpeechSegmenter(
            min_chars=stream_settings.ai_stream_segment_min_chars,
            max_chars=stream_settings.ai_stream_segment_max_chars,
        )
        first_token_ms: int | None = None
        stream_interrupted = False
        try:
            async for chunk in stream_reasoned_final_response(
                user_message=message,
                output_channel=source,
                decision=outcome.decision,
                tool_results=tool_results,
                context_items=context_items,
                conversation_history=history,
                user_preferences=preferences,
                confirmation_required=requires_confirmation,
                confirmation_message=confirmation_message,
                validation_errors=validation.errors,
                llm_stream=llm_chat_stream,
            ):
                _raise_if_cancelled(cancel_event)
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - response_started) * 1_000)
                parts.append(chunk)
                await event_sink(
                    {
                        "type": "reply_delta",
                        "text": chunk,
                        "metrics": {
                            "provider_first_token_ms": first_token_ms,
                            "first_reply_delta_ms": int(
                                (time.perf_counter() - turn_started) * 1_000
                            ),
                        },
                    }
                )
                for segment in segmenter.push(chunk):
                    await event_sink({"type": "speech_segment_ready", "text": segment})
        except (ReasoningContractError, RuntimeError, ValueError):
            stream_interrupted = bool(parts)
            log.exception("reasoning_final_response_stream_fallback partial=%s", stream_interrupted)
            if not parts:
                fallback = _fallback_final(
                    missing=outcome.decision.missing_information,
                    confirmation=confirmation_message,
                    tool_results=tool_results,
                )
                parts.append(fallback)
                await event_sink(
                    {"type": "reply_delta", "text": fallback, "metrics": {"fallback": True}}
                )
                for segment in segmenter.push(fallback):
                    await event_sink({"type": "speech_segment_ready", "text": segment})
        for segment in segmenter.flush():
            await event_sink({"type": "speech_segment_ready", "text": segment})
        reply = response_service._clean_user_facing_reply("".join(parts))
        if not reply:
            raise ReasoningContractError("Final streamed response was empty")
        outcome.metrics.final_response_ms = int(
            (time.perf_counter() - response_started) * 1_000
        )
        if stream_interrupted:
            validation.errors.append("Final response provider stream was interrupted")

    user_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="user",
        content=message,
        emotion=outcome.decision.emotion.emotion,
        intent=outcome.decision.primary_intent,
        mode=outcome.decision.mode.value,
        source=source[:32],
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user.id,
        role="assistant",
        content=reply,
        intent=outcome.decision.primary_intent,
        mode=outcome.decision.mode.value,
        source=source[:32],
    )
    db.add_all([user_message, assistant_message])
    conversation.mode = outcome.decision.mode.value
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    await memory_manager.index_row(db, user_message)
    await memory_manager.index_row(db, assistant_message)
    await conversation_service.append_turn(db, user.id, str(conversation.id), "user", message)
    await conversation_service.append_turn(db, user.id, str(conversation.id), "assistant", reply)

    plan_draft = next(
        (result.get("plan_draft") for result in tool_results if result.get("plan_draft")),
        None,
    )
    tool_actions = [
        {
            "type": result.get("tool"),
            "call_id": result.get("call_id"),
            "status": result.get("status"),
            "duration_ms": result.get("duration_ms", 0),
        }
        for result in tool_results
    ]
    if pending_call is not None:
        tool_actions.append(
            {"type": pending_call.name, "call_id": pending_call.call_id, "status": "awaiting_confirmation"}
        )
    outcome.metrics.total_ms = int((time.perf_counter() - turn_started) * 1_000)
    result = {
        "reply": reply,
        "mode": outcome.decision.mode.value,
        "intent": outcome.decision.primary_intent,
        "emotion": {
            **outcome.decision.emotion.model_dump(),
            "context": outcome.decision.conversation_strategy,
        },
        "ui_state": "awaiting_confirmation" if requires_confirmation else "idle",
        "memories_used": [
            {
                "id": item["id"],
                "type": item["source"],
                "title": item["text"][:120],
                "life_area": item.get("life_area"),
            }
            for item in context_items
            if item["source"] in {"memory", "recent_discussion"} and item.get("id")
        ],
        "suggested_actions": [],
        "tool_actions": tool_actions,
        "plan_draft": plan_draft,
        "requires_confirmation": requires_confirmation,
        "confirmation_prompt": confirmation_message,
        "conversation_id": conversation.id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
        "memory_metrics": merged.get("metrics", {}),
        "reasoning_metrics": outcome.metrics.model_dump(),
        "reasoning_validation_errors": validation.errors,
    }
    if pending_call is not None:
        result["pending_action"] = {
            "state": "awaiting_confirmation",
            "kind": "tool_call",
            "intent": outcome.decision.primary_intent,
            "fields": {"tool_call": pending_call.model_dump(mode="json")},
            "requires_confirmation": True,
        }
    return ReasonedTurnAttempt(result=result)


async def stream_reasoned_turn(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None,
    source: str,
    source_context: dict[str, Any] | None,
    preloaded_context: dict[str, Any] | None,
    cancel_event: asyncio.Event | None,
) -> AsyncIterator[dict[str, Any]]:
    """Expose live events while retaining one durable reasoning implementation."""
    queue: asyncio.Queue[dict[str, Any] | object] = asyncio.Queue(maxsize=8)
    sentinel = object()
    result: ReasonedTurnAttempt | None = None

    async def emit(event: dict[str, Any]) -> None:
        _raise_if_cancelled(cancel_event)
        await queue.put(event)

    async def run() -> None:
        nonlocal result
        try:
            result = await try_run_reasoned_turn(
                db,
                user,
                message,
                conversation_id=conversation_id,
                source=source,
                source_context=source_context,
                preloaded_context=preloaded_context,
                cancel_event=cancel_event,
                event_sink=emit,
            )
        finally:
            await queue.put(sentinel)

    task = asyncio.create_task(run(), name=f"reasoned-stream-{conversation_id or 'new'}")
    try:
        while True:
            item = await queue.get()
            if item is sentinel:
                break
            yield item  # type: ignore[misc]
        await task
        if result is not None and result.result is not None:
            yield {"type": "turn_complete", **result.result}
        elif result is not None:
            yield {
                "type": "stream_fallback_required",
                "reason": result.fallback_reason,
            }
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
