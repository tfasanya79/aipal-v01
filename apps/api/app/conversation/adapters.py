"""Unified streaming adapter for every conversation modality."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ..services.companion_orchestrator import get_companion_orchestrator
from .contracts import ConversationInput, InputModality, OrchestrationContext


class UnifiedConversationBrainAdapter:
    """Expose the one reasoning/tool implementation as canonical live events."""

    async def stream(
        self,
        request: ConversationInput,
        context: OrchestrationContext,
    ) -> AsyncIterator[dict[str, Any]]:
        source = {
            InputModality.TEXT: "text",
            InputModality.LIVE_VOICE: "voice",
            InputModality.UPLOADED_AUDIO: "voice",
            InputModality.VISION: "vision",
            InputModality.PHONE_CALL: "voice",
        }[request.modality]
        source_context = dict(request.source_context or {})
        if context.conversation_state is not None:
            source_context["conversation_state"] = context.conversation_state
        if context.preloaded_context is not None:
            source_context["preloaded_context"] = context.preloaded_context
        if context.cancel_event is not None:
            source_context["_cancel_event"] = context.cancel_event
        async for event in get_companion_orchestrator().run_turn_stream(
            context.db,
            context.user,
            request.text,
            conversation_id=request.conversation_id,
            source=source,
            source_context=source_context,
            preloaded_context=context.preloaded_context,
            cancel_event=context.cancel_event,
        ):
            yield event


# Import compatibility for extensions compiled against the Phase 1 name.
LegacyCompanionBrainAdapter = UnifiedConversationBrainAdapter
