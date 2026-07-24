"""Deterministic validation and confirmation policy for AI reasoning output."""

from __future__ import annotations

import time
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from ..conversation.reasoning import (
    PendingActionResolution,
    ReasoningDecision,
    ReasoningToolCall,
)
from .tool_registry import ToolArgumentError, UnknownToolError, tool_registry


class ReasoningValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executable_calls: list[ReasoningToolCall] = Field(default_factory=list)
    pending_call: ReasoningToolCall | None = None
    discarded_pending: bool = False
    discarded_call: ReasoningToolCall | None = None
    errors: list[str] = Field(default_factory=list)
    validation_ms: int = Field(default=0, ge=0)


def _pending_call(state: Mapping[str, Any] | None) -> ReasoningToolCall | None:
    if not state:
        return None
    pending = state.get("pending_action")
    if not isinstance(pending, Mapping):
        return None
    fields = pending.get("fields")
    if not isinstance(fields, Mapping):
        return None
    raw_call = fields.get("tool_call")
    if not isinstance(raw_call, Mapping):
        return None
    try:
        return ReasoningToolCall.model_validate(raw_call)
    except ValueError:
        return None


def validate_reasoning_decision(
    decision: ReasoningDecision,
    *,
    conversation_state: Mapping[str, Any] | None,
) -> ReasoningValidation:
    started = time.perf_counter()
    errors: list[str] = []
    pending = _pending_call(conversation_state)

    if decision.pending_action_resolution == PendingActionResolution.DISCARD:
        if pending is None:
            errors.append("No durable pending action exists to discard")
        return ReasoningValidation(
            discarded_pending=pending is not None,
            discarded_call=pending,
            errors=errors,
            validation_ms=int((time.perf_counter() - started) * 1_000),
        )

    calls = list(decision.tool_calls)
    confirmed_call_id: str | None = None
    if decision.pending_action_resolution == PendingActionResolution.CONFIRM:
        if pending is None:
            errors.append("No durable pending action exists to confirm")
        else:
            calls = [pending, *calls]
            confirmed_call_id = pending.call_id

    executable: list[ReasoningToolCall] = []
    pending_call: ReasoningToolCall | None = None
    seen_ids: set[str] = set()
    for call in calls[:4]:
        if call.call_id in seen_ids:
            errors.append(f"Duplicate tool call ID: {call.call_id}")
            continue
        seen_ids.add(call.call_id)
        try:
            definition = tool_registry.definition(call.name)
        except UnknownToolError:
            errors.append(f"Unknown tool: {call.name}")
            continue
        unexpected = set(call.arguments) - set(definition.argument_names)
        if unexpected:
            errors.append(
                f"Unexpected arguments for {call.name}: {', '.join(sorted(unexpected))}"
            )
            continue
        try:
            tool_registry.validate_arguments(call.name, call.arguments)
        except ToolArgumentError as exc:
            errors.extend(f"{call.name}.{error}" for error in exc.errors)
            continue
        if (
            call.name == "planner_engine"
            and call.arguments.get("action") == "confirm_draft"
            and call.call_id != confirmed_call_id
        ):
            errors.append("Planner draft application requires a matching durable confirmation")
            continue
        needs_confirmation = (
            call.requires_confirmation and call.name != "planner_engine"
        ) or tool_registry.requires_confirmation(call.name, call.arguments)
        if needs_confirmation and call.call_id != confirmed_call_id:
            if pending_call is None:
                pending_call = call
            continue
        executable.append(call)

    return ReasoningValidation(
        executable_calls=executable,
        pending_call=pending_call,
        errors=errors,
        validation_ms=int((time.perf_counter() - started) * 1_000),
    )
