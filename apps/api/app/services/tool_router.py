"""Compatibility adapter over the authoritative conversational Tool Registry."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .companion_response_service import generate_policy_text
from .tool_registry import ToolExecutionContext, ToolRegistryError, tool_registry

log = logging.getLogger("aipal.tool_router")


def detect_companion_tool(message: str, source_context: dict[str, Any] | None) -> str | None:
    del message
    if not source_context:
        return None
    raw = str(source_context.get("tool") or source_context.get("intent") or "").strip()
    return tool_registry.resolve(raw)


async def execute_companion_tool(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    source_context: dict[str, Any] | None = None,
    narrate: bool = True,
) -> dict[str, Any] | None:
    """Execute explicit UI calls through the same path used by AI reasoning."""
    tool = detect_companion_tool(message, source_context)
    if tool is None:
        return None
    try:
        arguments = tool_registry.arguments_from_context(tool, source_context)
        requires_confirmation = tool_registry.requires_confirmation(tool, arguments)
    except ToolRegistryError as exc:
        log.warning("explicit_tool_validation_failed tool=%s failure=%s", tool, type(exc).__name__)
        return {
            "reply": "I couldn’t validate that tool request. Please check the selected item and try again.",
            "mode": "assistant",
            "ui_state": "idle",
            "tool": tool,
            "tool_action": "validation_failed",
            "tool_result": None,
            "suggested_actions": [],
            "requires_confirmation": False,
        }
    if requires_confirmation:
        call_id = str((source_context or {}).get("call_id") or f"explicit_{uuid.uuid4().hex[:16]}")
        prompt = str((source_context or {}).get("confirmation_prompt") or "Would you like me to continue with that action?")
        return {
            "reply": prompt,
            "mode": "assistant",
            "ui_state": "awaiting_confirmation",
            "tool": tool,
            "tool_action": "awaiting_confirmation",
            "tool_result": None,
            "suggested_actions": [],
            "requires_confirmation": True,
            "confirmation_prompt": prompt,
            "pending_action": {
                "state": "awaiting_confirmation",
                "kind": "tool_call",
                "intent": tool,
                "fields": {
                    "tool_call": {
                        "call_id": call_id,
                        "name": tool,
                        "arguments": arguments,
                        "depends_on": [],
                        "rationale": "Explicit UI capability request.",
                        "requires_confirmation": True,
                    }
                },
                "requires_confirmation": True,
            },
        }
    try:
        result = await tool_registry.execute(
            ToolExecutionContext(
                db=db,
                user=user,
                message=message,
                source=str((source_context or {}).get("source") or "text"),
                source_context=source_context,
                call_id=str((source_context or {}).get("call_id") or "") or None,
            ),
            tool,
            arguments,
        )
    except ToolRegistryError:
        raise
    payload = result.public_payload()
    if narrate and result.narration_prompt and result.narration_evidence:
        try:
            payload["reply"] = (
                await generate_policy_text(
                    result.narration_prompt,
                    result.narration_evidence,
                    output_channel=str((source_context or {}).get("source") or "text"),
                )
            ).strip()
        except RuntimeError:
            pass
    return payload
