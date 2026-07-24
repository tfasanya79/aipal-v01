from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..llm_provider import llm_chat, llm_chat_stream
from .emotion_service import detect_emotion
from .mode_router import classify_mode
from .prompt_builder import PromptBuildRequest, prompt_builder
from .prompt_policy import sanitize_untrusted_text
from .tool_registry import tool_registry

log = logging.getLogger("aipal.companion_response")
conversation_llm_stream = llm_chat_stream

_MAX_CONTEXT_ITEMS = 10
_ACTION_WORDS = (
    "add",
    "create",
    "schedule",
    "remind me",
    "set a reminder",
    "make this a task",
    "turn this into a task",
)
_SOURCE_WEIGHTS = {
    "commitment": 2.6,
    "goal": 2.4,
    "project": 2.1,
    "memory": 2.0,
    "person": 1.7,
    "emotional_pattern": 1.6,
    "task": 1.4,
    "history": 1.2,
}
_SOURCE_LIMITS = {
    "memory": 4,
    "history": 3,
    "commitment": 3,
    "goal": 3,
    "project": 2,
    "person": 2,
    "emotional_pattern": 2,
    "task": 2,
}


async def generate_policy_text(
    prompt: str,
    evidence: list[str],
    *,
    output_channel: str = "text",
) -> str:
    """Narrate validated tool evidence through the canonical prompt engine."""
    messages = prompt_builder.build(
        PromptBuildRequest(
            user_message=prompt,
            output_channel=output_channel,
            purpose="tool_result",
            mode="assistant",
            tool_evidence=evidence,
            available_tools=tool_registry.names,
        )
    )
    return await llm_chat(messages)
_VALID_MODES = {"companion", "coach", "planner", "assistant", "reflection"}
_METADATA_LINE = re.compile(
    r"^\s*(mode|emotion|suggested_actions|should_create_task|memory_suggestions|context_items_used)\s*[:=]",
    re.IGNORECASE,
)


class StructuredAction(BaseModel):
    type: str
    label: str
    description: str = ""
    requires_confirmation: bool = False


class StructuredCompanionOutput(BaseModel):
    reply: str = Field(min_length=1)
    mode: str | None = None
    suggested_actions: list[StructuredAction] = Field(default_factory=list)
    should_create_task: bool | None = None
    memory_suggestions: list[dict[str, Any]] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(UTC)


def _as_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    if isinstance(item, dict):
        return dict(item)
    out: dict[str, Any] = {}
    for key in (
        "id",
        "source_type",
        "title",
        "name",
        "content",
        "description",
        "type",
        "entity_type",
        "life_area",
        "status",
        "importance",
        "confidence",
        "approval_status",
        "user_approved",
        "memory_scope",
        "expires_at",
        "created_at",
        "updated_at",
        "due_at",
        "follow_up_at",
        "summary",
        "emotion",
        "pattern_type",
    ):
        if hasattr(item, key):
            out[key] = getattr(item, key)
    return out


def _as_aware(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _memory_is_usable(item: dict[str, Any]) -> bool:
    if str(item.get("approval_status") or "approved") != "approved":
        return False
    if item.get("user_approved") is False:
        return False
    expires_at = _as_aware(item.get("expires_at"))
    if expires_at is not None and expires_at <= _now():
        return False
    return True


def _text_for(item: dict[str, Any]) -> str:
    fields = [
        item.get("title"),
        item.get("name"),
        item.get("content"),
        item.get("description"),
        item.get("summary"),
        item.get("follow_up_prompt"),
        item.get("life_area"),
        item.get("type"),
        item.get("entity_type"),
    ]
    return " ".join(str(field) for field in fields if field).strip()


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}


def _phrase_boost(user_message: str, item_text: str) -> float:
    user_lower = user_message.lower()
    item_lower = item_text.lower()
    boost = 0.0
    for phrase in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:\s+[A-Za-z][A-Za-z0-9]*){1,3}", user_message):
        if phrase.lower() in item_lower:
            boost += 2.5
    if item_lower and item_lower in user_lower:
        boost += 3.0
    return boost


def _score_context(user_message: str, item: dict[str, Any], source: str) -> float:
    item_text = _text_for(item)
    user_tokens = _tokens(user_message)
    item_tokens = _tokens(item_text)
    overlap = len(user_tokens & item_tokens)
    coverage = overlap / max(len(user_tokens), 1)
    score = _SOURCE_WEIGHTS.get(source, 1.0)
    score += overlap * 1.4
    score += coverage * 4.0
    score += _phrase_boost(user_message, item_text)
    score += min(float(item.get("importance") or 0), 10.0) * 0.28
    score += min(float(item.get("confidence") or 0), 1.0) * 1.8
    created_at = _as_aware(item.get("updated_at") or item.get("created_at") or item.get("due_at") or item.get("follow_up_at"))
    if created_at is not None:
        age_days = max((_now() - created_at).days, 0)
        score += max(0.0, 2.5 - min(age_days / 10, 2.5))
    if source == "memory" and not _memory_is_usable(item):
        return -1.0
    return score


def _collect_context_items(
    user_message: str,
    *,
    conversation_history: list[dict],
    tasks: list[dict],
    memories: list[dict],
    goals: list[dict],
    commitments: list[dict],
    projects: list[dict],
    people: list[dict],
    emotional_patterns: list[dict],
) -> list[dict[str, str]]:
    raw_sources = [
        ("history", conversation_history[-4:]),
        ("task", tasks),
        ("memory", memories),
        ("goal", goals),
        ("commitment", commitments),
        ("project", projects),
        ("person", people),
        ("emotional_pattern", emotional_patterns),
    ]
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for source, items in raw_sources:
        for raw in items or []:
            item = _as_dict(raw)
            if source == "memory" and not _memory_is_usable(item):
                continue
            text = _text_for(item)
            if not text:
                continue
            scored.append((_score_context(user_message, item, source), source, item))
    scored.sort(key=lambda row: row[0], reverse=True)
    selected: list[dict[str, str]] = []
    source_counts: dict[str, int] = defaultdict(int)
    seen_text: set[str] = set()
    for score, source, item in scored:
        if len(selected) >= _MAX_CONTEXT_ITEMS:
            break
        if score <= 0:
            continue
        if source_counts[source] >= _SOURCE_LIMITS.get(source, 2):
            continue
        text = sanitize_untrusted_text(_text_for(item)[:260])
        normalized = text.lower()
        if normalized in seen_text:
            continue
        seen_text.add(normalized)
        source_counts[source] += 1
        selected.append(
            {
                "source": str(item.get("source_type") or source),
                "text": text,
                "score": f"{score:.2f}",
            }
        )
    return selected


def _should_create_task(user_message: str, mode: str) -> bool:
    lower = user_message.lower()
    if mode != "assistant":
        return False
    return any(word in lower for word in _ACTION_WORDS)


def _suggested_actions(user_message: str, mode: str, should_create_task: bool) -> list[dict[str, object]]:
    if should_create_task:
        return [
            {
                "type": "create_task",
                "label": "Create task",
                "description": "Turn this into a tracked task after confirmation.",
                "requires_confirmation": True,
            }
        ]
    if mode in {"companion", "coach"}:
        return [
            {
                "type": "reflect",
                "label": "Keep talking",
                "description": "Stay in the conversation and think it through.",
                "requires_confirmation": False,
            }
        ]
    return []


def _memory_suggestions(memories: list[dict]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for raw in memories:
        item = _as_dict(raw)
        if _memory_is_usable(item):
            continue
        confidence = float(item.get("confidence") or 0)
        if confidence and confidence < 0.72:
            suggestions.append(
                {
                    "title": item.get("title") or item.get("name") or "Possible memory",
                    "reason": "Low confidence memory should be confirmed before use.",
                    "confidence": confidence,
                }
            )
    return suggestions[:3]


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", stripped)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_structured_output(text: str) -> StructuredCompanionOutput | None:
    payload = _extract_json_object(text)
    if payload is None:
        return None
    try:
        return StructuredCompanionOutput.model_validate(payload)
    except ValidationError:
        return None


def _clean_user_facing_reply(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""

    payload = _extract_json_object(stripped)
    if isinstance(payload, dict):
        reply = payload.get("reply") or payload.get("response") or payload.get("message")
        if isinstance(reply, str) and reply.strip():
            return _clean_user_facing_reply(reply)

    stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
    stripped = re.sub(r"\s*```$", "", stripped)
    lines = []
    for line in stripped.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if _METADATA_LINE.match(clean):
            continue
        if clean.lower().startswith("reply:"):
            clean = clean.split(":", 1)[1].strip()
        lines.append(clean)
    cleaned = " ".join(lines).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or stripped


def _safe_structured_actions(actions: list[StructuredAction], *, backend_should_create_task: bool) -> list[dict[str, object]]:
    safe: list[dict[str, object]] = []
    for action in actions[:4]:
        data = action.model_dump()
        if data["type"] == "create_task" and not backend_should_create_task:
            data["requires_confirmation"] = True
            data["description"] = data["description"] or "Task creation needs clear user confirmation."
            continue
        safe.append(data)
    return safe


def _validated_tool_evidence(user_preferences: dict[str, Any]) -> list[str]:
    evidence: list[str] = []
    completed = str((user_preferences or {}).get("completed_action") or "").strip()
    clarification = str((user_preferences or {}).get("clarifying_action") or "").strip()
    if completed:
        evidence.append(f"Backend completed action: {completed}")
    if clarification:
        evidence.append(f"Backend requires this missing detail before acting: {clarification}")
    return evidence


async def generate_companion_response(
    user_message: str,
    conversation_history: list[dict],
    tasks: list[dict],
    memories: list[dict],
    goals: list[dict],
    commitments: list[dict],
    projects: list[dict],
    people: list[dict],
    emotional_patterns: list[dict],
    user_preferences: dict,
    *,
    output_channel: str = "text",
    llm: Callable[[list[dict[str, str]]], Awaitable[str]] | None = None,
) -> dict:
    """
    Generate a natural AiPal companion response using the OpenAI-compatible API.
    """
    emotion = detect_emotion(user_message)
    mode = classify_mode(user_message, str(emotion["emotion"]))
    should_create_task = _should_create_task(user_message, mode)
    context_items = _collect_context_items(
        user_message,
        conversation_history=conversation_history,
        tasks=tasks,
        memories=memories,
        goals=goals,
        commitments=commitments,
        projects=projects,
        people=people,
        emotional_patterns=emotional_patterns,
    )
    backend_actions = _suggested_actions(user_message, mode, should_create_task)
    backend_memory_suggestions = _memory_suggestions(memories)
    messages = prompt_builder.build(
        PromptBuildRequest(
            user_message=user_message,
            output_channel=output_channel,
            mode=mode,
            emotion=emotion,
            context_items=context_items,
            conversation_history=conversation_history,
            user_preferences=user_preferences,
            tool_evidence=_validated_tool_evidence(user_preferences),
            available_tools=tool_registry.names,
        )
    )
    try:
        raw_reply = await (llm or llm_chat)(messages)
        structured = _parse_structured_output(raw_reply)
        if structured is not None:
            reply = _clean_user_facing_reply(structured.reply)
            structured_mode = (structured.mode or mode).strip().lower()
            output_mode = structured_mode if structured_mode in _VALID_MODES else mode
            structured_should_create = bool(structured.should_create_task)
            output_should_create_task = should_create_task and structured_should_create
            structured_actions = _safe_structured_actions(
                structured.suggested_actions,
                backend_should_create_task=should_create_task,
            )
            suggested_actions = structured_actions or backend_actions
            memory_suggestions = structured.memory_suggestions[:3] or backend_memory_suggestions
        else:
            reply = _clean_user_facing_reply(raw_reply)
            output_mode = mode
            output_should_create_task = should_create_task
            suggested_actions = backend_actions
            memory_suggestions = backend_memory_suggestions
    except Exception as exc:
        log.exception("companion_response_llm_failed", exc_info=exc)
        reply = _fallback_reply(user_message, context_items, mode)
        output_mode = mode
        output_should_create_task = should_create_task
        suggested_actions = backend_actions
        memory_suggestions = backend_memory_suggestions
    return {
        "reply": reply,
        "mode": output_mode,
        "emotion": emotion,
        "suggested_actions": suggested_actions,
        "should_create_task": output_should_create_task,
        "memory_suggestions": memory_suggestions,
        "context_items_used": context_items,
    }


def _fallback_reply(user_message: str, context_items: list[dict[str, str]], mode: str) -> str:
    if context_items:
        top_context = ", ".join(item["text"] for item in context_items[:2] if item.get("text"))
        if top_context:
            return f"I’m here with you. I’m using what I know about {top_context} to help with that."
    lower = user_message.lower().strip()
    if any(word in lower for word in ("hello", "hi", "hey")):
        return "Hey, I’m here with you. What feels most important right now?"
    if mode in {"companion", "reflection"}:
        return "I’m here with you. What’s on your mind?"
    return "I’m here. Tell me a bit more and I’ll help."
