"""The single orchestration entry point for every conversation modality."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ..safety import crisis_reply, is_crisis_likely
from .contracts import ConversationEvent, ConversationInput, ConversationResult, OrchestrationContext
from .ports import ConversationBrainPort, ConversationStatePort, EventPublisherPort

log = logging.getLogger("aipal.conversation_orchestrator")


class ConversationCancelledError(asyncio.CancelledError):
    """Raised when a turn is cancelled before terminal completion."""


class ConversationOrchestrator:
    def __init__(
        self,
        brain: ConversationBrainPort,
        *,
        state_manager: ConversationStatePort | None = None,
        event_publisher: EventPublisherPort | None = None,
    ) -> None:
        self._brain = brain
        self._state_manager = state_manager
        self._event_publisher = event_publisher

    async def stream(
        self,
        request: ConversationInput,
        context: OrchestrationContext,
    ) -> AsyncIterator[ConversationEvent]:
        if request.user_id != context.user.id:
            raise ValueError("Conversation input user does not match authenticated user")

        sequence = 0

        async def envelope(
            event_type: str,
            payload: dict[str, Any],
            *,
            transient: bool = True,
        ) -> ConversationEvent:
            nonlocal sequence
            event_conversation_id = request.conversation_id
            raw_conversation_id = payload.get("conversation_id")
            if raw_conversation_id:
                try:
                    event_conversation_id = uuid.UUID(str(raw_conversation_id))
                except ValueError:
                    event_conversation_id = request.conversation_id
            event = ConversationEvent(
                event_type=event_type,
                sequence=sequence,
                input_id=request.input_id,
                turn_id=request.turn_id,
                user_id=request.user_id,
                conversation_id=event_conversation_id,
                correlation_id=request.input_id,
                causation_id=request.input_id,
                transient=transient,
                payload=payload,
            )
            sequence += 1
            if self._event_publisher is not None:
                await self._event_publisher.publish(event)
            return event

        self._raise_if_cancelled(context)
        if self._state_manager is not None:
            state = await self._state_manager.begin_turn(context.db, request)
            if state is not None:
                context.conversation_state = state.model_dump(mode="json")
        yield await envelope(
            "input_accepted",
            {"modality": request.modality.value, "received_at": request.received_at.isoformat()},
        )

        transition = dict(
            ((context.conversation_state or {}).get("metadata") or {}).get(
                "topic_transition"
            )
            or {}
        )
        classification = str(transition.get("classification") or "")
        if classification in {"ambiguous_transition", "cancel_active_request"}:
            reply = (
                "That turn was already processed."
                if transition.get("reason_code") == "duplicate_user_event_rejected"
                else "Which active request should I change?"
                if classification == "ambiguous_transition"
                else "Okay, I cancelled the active request."
            )
            terminal = {
                "reply": reply,
                "mode": "companion",
                "intent": classification,
                "emotion": {"emotion": "neutral", "intensity": 1, "context": ""},
                "ui_state": "idle",
                "memories_used": [],
                "suggested_actions": [],
                "tool_actions": [],
                "plan_draft": None,
                "requires_confirmation": False,
                "confirmation_prompt": None,
                "conversation_id": str(request.conversation_id),
                "topic_transition": transition,
                "metrics": {"topic_transition": transition},
            }
            yield await envelope("reply_delta", {"text": reply})
            yield await envelope("sentence_ready", {"text": reply})
            if self._state_manager is not None:
                state = await self._state_manager.complete_turn(
                    context.db, request, terminal
                )
                context.conversation_state = state.model_dump(mode="json")
            yield await envelope("turn_complete", terminal, transient=False)
            return

        if is_crisis_likely(request.text):
            reply = crisis_reply()
            terminal = {
                "reply": reply,
                "crisis": True,
                "mode": "companion",
                "emotion": {
                    "emotion": "neutral",
                    "intensity": 1,
                    "context": "Crisis-safe response.",
                },
                "ui_state": "idle",
                "memories_used": [],
                "suggested_actions": [],
                "tool_actions": [],
                "plan_draft": None,
                "requires_confirmation": False,
                "confirmation_prompt": None,
                "conversation_id": str(request.conversation_id),
                "metrics": {},
            }
            yield await envelope("reply_delta", {"text": reply})
            yield await envelope("sentence_ready", {"text": reply})
            if self._state_manager is not None:
                state = await self._state_manager.complete_turn(context.db, request, terminal)
                context.conversation_state = state.model_dump(mode="json")
            yield await envelope(
                "turn_complete",
                terminal,
                transient=False,
            )
            return

        try:
            async for raw_event in self._brain.stream(request, context):
                self._raise_if_cancelled(context)
                raw = dict(raw_event)
                event_type = str(raw.pop("type", "internal_event"))
                if event_type in {"turn_complete", "turn_meta"} and self._state_manager is not None:
                    raw.setdefault("topic_transition", transition)
                    metrics = dict(raw.get("metrics") or {})
                    metrics["topic_transition"] = {
                        "classification": transition.get("classification"),
                        "confidence": transition.get("confidence"),
                        "reason_code": transition.get("reason_code"),
                        "classifier_latency_ms": transition.get(
                            "classifier_latency_ms"
                        ),
                        "fallback_reason": transition.get("fallback_reason"),
                    }
                    raw["metrics"] = metrics
                    state = await self._state_manager.complete_turn(context.db, request, raw)
                    context.conversation_state = state.model_dump(mode="json")
                yield await envelope(
                    event_type,
                    raw,
                    transient=event_type not in {"turn_complete", "turn_cancelled"},
                )
        except asyncio.CancelledError:
            if self._state_manager is not None:
                try:
                    await asyncio.shield(self._state_manager.cancel_turn(context.db, request))
                except Exception:
                    log.exception("conversation_state_cancel_update_failed turn=%s", request.turn_id)
            raise
        except Exception as exc:
            if self._state_manager is not None:
                try:
                    await self._state_manager.fail_turn(context.db, request, reason=type(exc).__name__)
                except Exception:
                    log.exception("conversation_state_failure_update_failed turn=%s", request.turn_id)
            raise

    async def run(
        self,
        request: ConversationInput,
        context: OrchestrationContext,
    ) -> ConversationResult:
        terminal: dict[str, Any] | None = None
        reply_parts: list[str] = []
        async for event in self.stream(request, context):
            if event.event_type == "reply_delta":
                reply_parts.append(str(event.payload.get("text") or ""))
            if event.event_type in {"turn_complete", "turn_meta"}:
                terminal = dict(event.payload)
        if terminal is None:
            raise RuntimeError("Conversation brain completed without a terminal event")
        terminal.setdefault("reply", "".join(reply_parts).strip())
        return ConversationResult.model_validate(terminal)

    @staticmethod
    def _raise_if_cancelled(context: OrchestrationContext) -> None:
        if context.cancel_event is not None and context.cancel_event.is_set():
            raise ConversationCancelledError()
