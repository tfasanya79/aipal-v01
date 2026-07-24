"""Versioned contracts for Phase 7 model-driven conversation reasoning."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConversationMode(StrEnum):
    COMPANION = "companion"
    COACH = "coach"
    PLANNER = "planner"
    ASSISTANT = "assistant"
    REFLECTION = "reflection"
    LEARNING = "learning"
    CREATIVE = "creative"
    DECISION_SUPPORT = "decision_support"


class PendingActionResolution(StrEnum):
    NONE = "none"
    CONFIRM = "confirm"
    DISCARD = "discard"


class IntentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)


class EmotionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    emotion: str = Field(default="neutral", min_length=1, max_length=40)
    intensity: int = Field(default=1, ge=1, le=10)
    urgency: int = Field(default=0, ge=0, le=10)


class ReasoningToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str = Field(min_length=1, max_length=48, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict, max_length=20)
    depends_on: list[str] = Field(default_factory=list, max_length=4)
    rationale: str = Field(default="", max_length=240)
    requires_confirmation: bool = False


class ReasoningDecision(BaseModel):
    """Strict model output; deliberately excludes hidden chain-of-thought."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    intents: list[IntentAssessment] = Field(min_length=1, max_length=5)
    primary_intent: str = Field(min_length=1, max_length=80)
    missing_information: list[str] = Field(default_factory=list, max_length=5)
    mode: ConversationMode = ConversationMode.COMPANION
    emotion: EmotionAssessment = Field(default_factory=EmotionAssessment)
    conversation_strategy: str = Field(min_length=1, max_length=240)
    response_strategy: str = Field(min_length=1, max_length=240)
    planning_notes: list[str] = Field(default_factory=list, max_length=6)
    tool_calls: list[ReasoningToolCall] = Field(default_factory=list, max_length=4)
    confirmation_message: str | None = Field(default=None, max_length=300)
    pending_action_resolution: PendingActionResolution = PendingActionResolution.NONE

    @field_validator("missing_information", "planning_notes")
    @classmethod
    def clean_bounded_strings(cls, values: list[str]) -> list[str]:
        return [value.strip()[:300] for value in values if value.strip()]

    @model_validator(mode="after")
    def calls_are_ordered_and_unique(self) -> "ReasoningDecision":
        indexes: dict[str, int] = {}
        for index, call in enumerate(self.tool_calls):
            if call.call_id in indexes:
                raise ValueError("Tool call IDs must be unique")
            indexes[call.call_id] = index
            for dependency in call.depends_on:
                if dependency not in indexes:
                    raise ValueError("Tool dependencies must reference an earlier call")
        return self


class ReasoningMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasoning_ms: int = Field(ge=0)
    validation_ms: int = Field(default=0, ge=0)
    tool_execution_ms: int = Field(default=0, ge=0)
    final_response_ms: int = Field(default=0, ge=0)
    total_ms: int = Field(default=0, ge=0)
    used_compatibility_fallback: bool = False
    fallback_reason: str | None = None


class ReasoningOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: ReasoningDecision
    metrics: ReasoningMetrics
