"""Phase 1 boundaries for the unified conversation architecture.

These protocols deliberately wrap current implementations. Their internals are
replaced only in the dedicated later phases.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol

from .contracts import ConversationEvent, ConversationInput, OrchestrationContext


class ConversationBrainPort(Protocol):
    def stream(
        self, request: ConversationInput, context: OrchestrationContext
    ) -> AsyncIterator[dict[str, Any]]: ...


class ConversationStatePort(Protocol):
    async def begin_turn(self, db: Any, request: ConversationInput) -> Any: ...
    async def complete_turn(self, db: Any, request: ConversationInput, terminal: dict[str, Any]) -> Any: ...
    async def cancel_turn(self, db: Any, request: ConversationInput) -> Any: ...
    async def fail_turn(self, db: Any, request: ConversationInput, *, reason: str) -> Any: ...


class MemoryManagerPort(Protocol):
    async def retrieve_stable(self, db: Any, user: Any, *, conversation_id: Any = None) -> Mapping[str, Any]: ...
    async def retrieve_query(self, db: Any, user_id: Any, query: str, *, limit: int = 16) -> Mapping[str, Any]: ...
    def merge(self, stable: Mapping[str, Any], query: Mapping[str, Any]) -> Mapping[str, Any]: ...


class PromptBuilderPort(Protocol):
    def build(self, request: Any) -> Sequence[Mapping[str, Any]]: ...


class PlanningEnginePort(Protocol):
    async def plan(self, request: ConversationInput, context: Mapping[str, Any]) -> Mapping[str, Any]: ...


class ToolExecutorPort(Protocol):
    async def execute(
        self,
        context: Any,
        name: str,
        arguments: Mapping[str, Any],
        *,
        allow_alias: bool = False,
    ) -> Any: ...


class LLMPort(Protocol):
    def stream(self, messages: Sequence[Mapping[str, Any]]) -> AsyncIterator[str]: ...


class STTPort(Protocol):
    async def transcribe(self, audio: bytes) -> Mapping[str, Any]: ...


class TTSPort(Protocol):
    def stream(self, text: str, *, voice: str) -> AsyncIterator[tuple[bytes, str]]: ...


class EventPublisherPort(Protocol):
    async def publish(self, event: ConversationEvent) -> None: ...
