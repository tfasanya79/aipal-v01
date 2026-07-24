"""Model-driven reasoning and final-response stages for Phase 7."""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Mapping

from ..conversation.reasoning import (
    ReasoningDecision,
    ReasoningMetrics,
    ReasoningOutcome,
)
from ..config import get_settings
from .prompt_builder import PromptBuildRequest, prompt_builder
from .tool_registry import tool_registry

LLMCallable = Callable[..., Awaitable[str]]
LLMStreamCallable = Callable[..., AsyncIterator[str]]


class ReasoningContractError(RuntimeError):
    pass


def _parse_decision(raw: str) -> ReasoningDecision:
    text = (raw or "").strip()
    if len(text) > 64_000:
        raise ReasoningContractError("Reasoning response exceeded 64 KB")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReasoningContractError("Reasoning response was not strict JSON") from exc
    if not isinstance(payload, dict):
        raise ReasoningContractError("Reasoning response must be a JSON object")
    try:
        return ReasoningDecision.model_validate(payload)
    except ValueError as exc:
        raise ReasoningContractError("Reasoning response failed schema validation") from exc


async def reason_about_turn(
    *,
    user_message: str,
    output_channel: str,
    context_items: list[dict[str, Any]],
    conversation_history: list[dict[str, Any]],
    user_preferences: dict[str, Any],
    conversation_state: Mapping[str, Any] | None,
    llm: LLMCallable,
) -> ReasoningOutcome:
    started = time.perf_counter()
    messages = prompt_builder.build(
        PromptBuildRequest(
            user_message=user_message,
            output_channel=output_channel,
            purpose="reasoning",
            mode=str((conversation_state or {}).get("conversation_mode") or "companion"),
            emotion=dict((conversation_state or {}).get("current_emotion") or {}),
            context_items=context_items,
            conversation_history=conversation_history,
            user_preferences=user_preferences,
            available_tools=tool_registry.names,
            tool_instructions=tool_registry.instructions,
            response_schema=ReasoningDecision.model_json_schema(),
            runtime_context=dict(conversation_state or {}),
        )
    )
    decision = _parse_decision(
        await llm(
            messages,
            max_tokens=get_settings().ai_reasoning_max_tokens,
            timeout_seconds=get_settings().ai_reasoning_timeout_seconds,
            response_schema=ReasoningDecision.model_json_schema(),
        )
    )
    return ReasoningOutcome(
        decision=decision,
        metrics=ReasoningMetrics(
            reasoning_ms=int((time.perf_counter() - started) * 1_000)
        ),
    )


async def generate_reasoned_final_response(
    *,
    user_message: str,
    output_channel: str,
    decision: ReasoningDecision,
    tool_results: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    conversation_history: list[dict[str, Any]],
    user_preferences: dict[str, Any],
    confirmation_required: bool,
    confirmation_message: str | None,
    validation_errors: list[str],
    llm: LLMCallable,
) -> tuple[str, int]:
    started = time.perf_counter()
    messages = _reasoned_final_messages(
        user_message=user_message,
        output_channel=output_channel,
        decision=decision,
        tool_results=tool_results,
        context_items=context_items,
        conversation_history=conversation_history,
        user_preferences=user_preferences,
        confirmation_required=confirmation_required,
        confirmation_message=confirmation_message,
        validation_errors=validation_errors,
    )
    reply = (await llm(messages)).strip()
    if not reply:
        raise ReasoningContractError("Final response was empty")
    return reply, int((time.perf_counter() - started) * 1_000)


async def stream_reasoned_final_response(
    *,
    user_message: str,
    output_channel: str,
    decision: ReasoningDecision,
    tool_results: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    conversation_history: list[dict[str, Any]],
    user_preferences: dict[str, Any],
    confirmation_required: bool,
    confirmation_message: str | None,
    validation_errors: list[str],
    llm_stream: LLMStreamCallable,
) -> AsyncIterator[str]:
    messages = _reasoned_final_messages(
        user_message=user_message,
        output_channel=output_channel,
        decision=decision,
        tool_results=tool_results,
        context_items=context_items,
        conversation_history=conversation_history,
        user_preferences=user_preferences,
        confirmation_required=confirmation_required,
        confirmation_message=confirmation_message,
        validation_errors=validation_errors,
    )
    emitted = False
    async for chunk in llm_stream(messages):
        if chunk:
            emitted = True
            yield chunk
    if not emitted:
        raise ReasoningContractError("Final response stream was empty")


def _reasoned_final_messages(
    *,
    user_message: str,
    output_channel: str,
    decision: ReasoningDecision,
    tool_results: list[dict[str, Any]],
    context_items: list[dict[str, Any]],
    conversation_history: list[dict[str, Any]],
    user_preferences: dict[str, Any],
    confirmation_required: bool,
    confirmation_message: str | None,
    validation_errors: list[str],
) -> list[dict[str, str]]:
    decision_evidence = {
        "primary_intent": decision.primary_intent,
        "intents": [item.model_dump() for item in decision.intents],
        "mode": decision.mode.value,
        "emotion": decision.emotion.model_dump(),
        "missing_information": decision.missing_information,
        "conversation_strategy": decision.conversation_strategy,
        "response_strategy": decision.response_strategy,
        "planning_notes": decision.planning_notes,
        "confirmation_required": confirmation_required,
        "confirmation_message": confirmation_message,
        "validation_errors": validation_errors,
    }
    evidence = [
        f"Validated decision: {json.dumps(decision_evidence, default=str, sort_keys=True)[:4_000]}"
    ]
    evidence.extend(
        f"Tool result: {json.dumps(result, default=str, sort_keys=True)[:2_000]}"
        for result in tool_results[:4]
    )
    return prompt_builder.build(
        PromptBuildRequest(
            user_message=user_message,
            output_channel=output_channel,
            purpose="final_response",
            mode=decision.mode.value,
            emotion=decision.emotion.model_dump(),
            context_items=context_items,
            conversation_history=conversation_history,
            user_preferences=user_preferences,
            tool_evidence=evidence,
            available_tools=tool_registry.names,
        )
    )
