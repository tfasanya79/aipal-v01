"""Canonical conversation architecture.

All user-facing modalities enter the AI brain through this package. Existing
subsystems are exposed through adapters until their dedicated rebuild phases.
"""

from .contracts import (
    ConversationEvent,
    ConversationInput,
    ConversationResult,
    InputModality,
    OrchestrationContext,
)
from .state import ConversationState, ConversationStatePatch, conversation_state_manager


def get_conversation_orchestrator():
    """Resolve the composition root lazily to keep contracts dependency-free."""
    from .dependencies import get_conversation_orchestrator as resolve

    return resolve()

__all__ = [
    "ConversationEvent",
    "ConversationInput",
    "ConversationResult",
    "InputModality",
    "OrchestrationContext",
    "ConversationState",
    "ConversationStatePatch",
    "conversation_state_manager",
    "get_conversation_orchestrator",
]
