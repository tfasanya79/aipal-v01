"""Composition root for the unified conversation architecture."""

from __future__ import annotations

from .adapters import UnifiedConversationBrainAdapter
from .orchestrator import ConversationOrchestrator
from .state import conversation_state_manager

_ORCHESTRATOR = ConversationOrchestrator(
    UnifiedConversationBrainAdapter(),
    state_manager=conversation_state_manager,
)


def get_conversation_orchestrator() -> ConversationOrchestrator:
    return _ORCHESTRATOR
