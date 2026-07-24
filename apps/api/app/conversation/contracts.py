"""Versioned contracts shared by every conversation transport."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User


class InputModality(StrEnum):
    TEXT = "text"
    LIVE_VOICE = "live_voice"
    UPLOADED_AUDIO = "uploaded_audio"
    VISION = "vision"
    PHONE_CALL = "phone_call"


class ConversationInput(BaseModel):
    """Transport-neutral input accepted by the one conversation brain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    input_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    modality: InputModality
    text: str
    source_context: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()


class ConversationEvent(BaseModel):
    """Ordered event envelope emitted by the conversation orchestrator."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str
    sequence: int = Field(ge=0)
    input_id: uuid.UUID
    turn_id: str
    user_id: uuid.UUID
    conversation_id: uuid.UUID | None = None
    correlation_id: uuid.UUID
    causation_id: uuid.UUID
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    transient: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_transport(self) -> dict[str, Any]:
        """Return the legacy wire shape while preserving the canonical envelope."""
        serialized = self.model_dump(mode="json")
        return {
            "type": self.event_type,
            **serialized["payload"],
            "event_id": serialized["event_id"],
            "sequence": self.sequence,
            "schema_version": self.schema_version,
        }


class ConversationResult(BaseModel):
    """Collected terminal result used by request/response transports."""

    model_config = ConfigDict(extra="allow")

    reply: str
    mode: str = "companion"
    emotion: dict[str, Any] = Field(
        default_factory=lambda: {"emotion": "neutral", "intensity": 1, "context": ""}
    )
    ui_state: str = "idle"
    memories_used: list[dict[str, Any]] = Field(default_factory=list)
    suggested_actions: list[dict[str, Any]] = Field(default_factory=list)
    tool_actions: list[Any] = Field(default_factory=list)
    plan_draft: Any | None = None
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    conversation_id: uuid.UUID | None = None
    crisis: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)


class OrchestrationContext:
    """Request-scoped runtime dependencies, kept outside serializable contracts."""

    __slots__ = ("db", "user", "cancel_event", "preloaded_context", "conversation_state")

    def __init__(
        self,
        *,
        db: AsyncSession,
        user: User,
        cancel_event: asyncio.Event | None = None,
        preloaded_context: dict[str, Any] | None = None,
    ) -> None:
        if user.id is None:
            raise ValueError("Persisted user required for conversation orchestration")
        self.db = db
        self.user = user
        self.cancel_event = cancel_event
        self.preloaded_context = preloaded_context
        self.conversation_state: dict[str, Any] | None = None
