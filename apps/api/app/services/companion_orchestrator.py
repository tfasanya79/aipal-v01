from __future__ import annotations

import asyncio
import re
import uuid
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, EmotionalPattern, Memory, Message, User
from ..config import get_settings
from ..services import plan_extractor
from ..services import plan_draft as draft_svc
from ..services import plan_intent
from ..services import conversation as conv_svc
from ..services.goal_service import list_active_goals
from ..services.coaching_service import coaching_context
from ..services.commitment_service import (
    extract_commitments,
    generate_commitment_followup,
    list_due_followups as list_due_commitments,
)
from ..services.proactive_conversation_service import generate_proactive_prompt, get_or_create_preferences, list_proactive_prompts
from ..services.memory_service import (
    extract_memories_from_message,
    persist_extracted_memories,
    recent_life_area_insight,
    relationship_context,
    summarize_recent_conversations,
)
from ..services.relationship_followup_service import generate_followup_prompt, list_due_followups
from ..services.tool_router import execute_companion_tool
from ..services.tool_registry import ToolExecutionContext, tool_registry
from ..services.mode_router import classify_mode
from ..services.emotion_service import detect_emotion
from ..services.profile_service import get_or_create_profile, profile_snapshot
from ..services.safety_service import is_safe_message, safe_reply
from ..services import tasks as task_svc
from ..services.turn_shared import draft_to_schema
from ..services.audit_service import record_audit
from ..services.companion_response_service import (
    _clean_user_facing_reply,
    generate_companion_response,
)
from ..services.context_cache import get_context_cache, set_context_cache
from ..services.memory_manager import memory_manager
from ..services.reasoned_turn_service import stream_reasoned_turn, try_run_reasoned_turn
from ..services.today_item_service import (
    ambiguous_agenda_request,
    extract_meeting_request,
    extract_reminder_request,
    get_today_item,
    reschedule_today_item,
)
from ..services.business_context_service import get_project
from ..services.project_room_service import get_room
from ..timezone_util import user_local_today
from .prompt_policy import sanitize_untrusted_text
from .tool_policy import is_tool_allowed


@dataclass(slots=True)
class TurnArtifacts:
    reply: str
    mode: str
    emotion: dict[str, object]
    memories_used: list[dict[str, object]]
    suggested_actions: list[dict[str, object]]
    plan_draft: dict | None
    requires_confirmation: bool
    confirmation_prompt: str | None
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID | None
    assistant_message_id: uuid.UUID | None


def _default_turn_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    payload.setdefault("reply", "")
    payload.setdefault("mode", "assistant")
    payload.setdefault("ui_state", "idle")
    payload.setdefault("emotion", {"emotion": "neutral", "intensity": 1, "context": "Tool routed turn."})
    payload.setdefault("memories_used", [])
    payload.setdefault("suggested_actions", [])
    payload.setdefault("plan_draft", None)
    payload.setdefault("requires_confirmation", False)
    payload.setdefault("confirmation_prompt", None)
    payload.setdefault("conversation_id", None)
    return payload


def _conversation_title(message: str) -> str:
    words = re.findall(r"\w+", message)
    if not words:
        return "Companion"
    title = " ".join(words[:5]).strip()
    return title[:60].title()


def _suggested_actions_for(
    mode: str,
    plan_draft: dict | None,
    message: str,
    *,
    commitment_detected: bool = False,
) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    lower = message.lower()
    if mode == "planner" and plan_draft and plan_draft.get("proposed_tasks"):
        actions.append(
            {
                "type": "review_plan",
                "label": "Review suggested plan",
                "description": "AiPal drafted tasks for your day.",
                "requires_confirmation": True,
            }
        )
    if not commitment_detected and mode == "assistant" and any(word in lower for word in ("remind", "add", "schedule", "task")):
        actions.append(
            {
                "type": "create_task",
                "label": "Create task",
                "description": "Turn this into a tracked task if you want.",
                "requires_confirmation": True,
            }
        )
    if mode in {"companion", "coach"}:
        actions.append(
            {
                "type": "reflect",
                "label": "Keep talking",
                "description": "Stay in conversation and explore this a bit more.",
                "requires_confirmation": False,
            }
        )
    return [action for action in actions if is_tool_allowed(mode, str(action.get("type")), "text")]


def _agenda_confirmation_draft(
    *,
    kind: str,
    title: str,
    due_at: datetime,
    source_text: str,
    estimated_minutes: int,
    end_at: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": kind,
        "title": title,
        "notes": source_text,
        "due_at": due_at.isoformat(),
        "estimated_minutes": estimated_minutes,
        "priority": 1,
        "category": kind,
    }
    if kind == "meeting":
        item["start_time"] = due_at.isoformat()
        item["end_time"] = (end_at or (due_at + timedelta(minutes=estimated_minutes))).isoformat()
    return {
        "intent": f"{kind}_confirmation",
        "proposed_tasks": [item],
        "clarifying_question": None,
    }


def _should_surface_commitments(message: str, mode: str, emotion: str, due_commitments: list[object]) -> bool:
    if mode not in {"companion", "coach", "reflection"}:
        return False
    lower = message.lower()
    if any(word in lower for word in ("urgent", "asap", "emergency", "help me", "add this", "task", "schedule this")):
        return False
    if len(lower.split()) <= 3:
        return True
    if emotion in {"sad", "anxious", "frustrated", "drained", "neutral"} and due_commitments:
        return True
    return False


def _life_area_suggestion(insight: dict[str, object] | None) -> dict[str, object] | None:
    if insight is None:
        return None
    return {
        "type": "life_area_checkin",
        "label": str(insight["text"]),
        "description": f"Recent memories point to {insight['life_area']} themes.",
        "requires_confirmation": False,
    }


def _context_uuid(source_context: dict[str, Any] | None, key: str) -> uuid.UUID | None:
    if not source_context:
        return None
    value = source_context.get(key)
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def _handle_source_context_action(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None,
    source: str,
    source_context: dict[str, Any] | None,
) -> dict[str, object] | None:
    if not source_context:
        return None
    text = sanitize_untrusted_text((message or "").strip())
    lower = text.lower()
    screen = str(source_context.get("screen") or "").lower()

    if screen == "today" and ("move this" in lower or "tomorrow" in lower):
        item_id = _context_uuid(source_context, "selected_item_id")
        if item_id is None:
            return None
        row = await get_today_item(db, user.id, item_id)
        if row is None:
            return None
        moved = await reschedule_today_item(db, user.id, item_id, datetime.now(UTC) + timedelta(days=1))
        if moved is None:
            return None
        conv = await _get_or_create_conversation(db, user.id, conversation_id, "assistant", text)
        reply = f"Done, I moved “{moved.title}” to tomorrow."
        result = await _store_simple_turn(db, conv, user.id, text, reply, source=source, mode="assistant")
        result["suggested_actions"] = [{"type": "rescheduled_today_item", "label": "Moved to tomorrow", "requires_confirmation": False}]
        return result

    if screen == "meeting" and "summarize this" in lower:
        from ..services.meeting_assistant_service import summarize_meeting

        meeting_id = _context_uuid(source_context, "selected_item_id") or _context_uuid(source_context, "selected_meeting_id")
        if meeting_id is None:
            return None
        summary = await summarize_meeting(db, user.id, meeting_id)
        reply = (
            str(summary.get("summary"))
            if summary and summary.get("summary")
            else "I don’t see notes for this meeting yet. Add a few notes first, and I’ll summarize them."
        )
        conv = await _get_or_create_conversation(db, user.id, conversation_id, "assistant", text)
        return await _store_simple_turn(db, conv, user.id, text, reply, source=source, mode="assistant")

    if screen in {"project", "project_room"} and "risk" in lower:
        project_id = _context_uuid(source_context, "selected_project_id") or _context_uuid(source_context, "selected_item_id")
        if project_id is None:
            return None
        room = await get_room(db, user.id, project_id)
        project = None if room else await get_project(db, user.id, project_id)
        target = room or project
        if target is None:
            return None
        risks = target.risks or []
        if isinstance(risks, dict):
            risk_text = ", ".join(f"{key}: {value}" for key, value in risks.items())
        elif isinstance(risks, list):
            risk_text = ", ".join(str(item) for item in risks)
        else:
            risk_text = ""
        reply = f"For {target.name}, the current risks are: {risk_text or 'No risks listed yet.'}"
        conv = await _get_or_create_conversation(db, user.id, conversation_id, "assistant", text)
        return await _store_simple_turn(db, conv, user.id, text, reply, source=source, mode="assistant")

    return None


def _should_surface_followups(message: str, mode: str, emotion: str, due_followups: list[Memory]) -> bool:
    if mode not in {"companion", "coach", "reflection"}:
        return False
    lower = message.lower()
    if any(word in lower for word in ("urgent", "asap", "emergency", "help me", "can you do this", "add this", "schedule this")):
        return False
    if len(lower.split()) <= 3:
        return True
    if emotion in {"sad", "anxious", "frustrated", "drained", "neutral"} and due_followups:
        return True
    return False


async def _run_turn_impl(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None = None,
    source: str = "text",
    preloaded_context: dict[str, Any] | None = None,
) -> dict[str, object]:
    text = sanitize_untrusted_text((message or "").strip())
    if not text:
        empty_emotion = {"emotion": "neutral", "intensity": 1, "context": "Empty message."}
        return {
            "reply": "I didn’t catch anything yet.",
            "mode": "companion",
            "emotion": empty_emotion,
            "memories_used": [],
            "suggested_actions": [],
            "plan_draft": None,
            "requires_confirmation": False,
            "confirmation_prompt": None,
            "conversation_id": conversation_id or uuid.uuid4(),
        }

    if not is_safe_message(text):
        reply = safe_reply(text)
        conv = await _get_or_create_conversation(db, user.id, conversation_id, "companion", text)
        return await _store_simple_turn(db, conv, user.id, text, reply, source=source, mode="companion")

    emotion = detect_emotion(text)
    recent_context = await _recent_context(db, user.id, conversation_id)
    mode = classify_mode(text, str(emotion["emotion"]), recent_context)

    conv = await _get_or_create_conversation(db, user.id, conversation_id, mode, text)
    local_day = user_local_today(user.timezone)
    tz = user.timezone or "UTC"
    pending_early = await draft_svc.get_draft(db, user.id)
    if pending_early and pending_early.get("proposed_tasks"):
        if plan_intent.is_confirm_intent(text):
            tool_result = await tool_registry.execute(
                ToolExecutionContext(
                    db=db,
                    user=user,
                    message=text,
                    source=source,
                    source_context={"tool": "planner_engine", "action": "confirm_draft"},
                    call_id=f"legacy_confirm_{conv.id}",
                ),
                "planner_engine",
                {"action": "confirm_draft"},
            )
            created = list((tool_result.tool_result or {}).get("created") or [])
            if created:
                names = ", ".join(c["title"] for c in created)
                reply = f"Done, I've added {names} to Today."
                action_label = f"Confirmed plan: {names}"
            else:
                reply = "Got it, those are already on Today."
                action_label = "Confirmed plan: duplicates skipped"
            result = await _store_simple_turn(db, conv, user.id, text, reply, source=source, mode=mode)
            result["suggested_actions"] = [
                {
                    "type": "confirmed_plan",
                    "label": action_label,
                    "description": action_label,
                    "requires_confirmation": False,
                }
            ]
            return result
        if plan_intent.is_discard_intent(text):
            await draft_svc.clear_draft(db, user.id)
            result = await _store_simple_turn(
                db,
                conv,
                user.id,
                text,
                "Okay, I won't add that plan to Today.",
                source=source,
                mode=mode,
            )
            result["suggested_actions"] = [
                {
                    "type": "discarded_plan",
                    "label": "Discarded plan draft",
                    "description": "Discarded plan draft",
                    "requires_confirmation": False,
                }
            ]
            return result
    fast_voice = source == "voice"
    if fast_voice:
        (
            preferences,
            goals,
            due_followups,
            due_commitments,
        ) = await asyncio.gather(
            get_or_create_preferences(db, user.id),
            list_active_goals(db, user.id),
            list_due_followups(db, user.id, limit=2),
            list_due_commitments(db, user.id),
        )
        profile = {"summary": user.about_me or ""}
        recent_summary = ""
        relationship_rows: dict[str, list[Memory]] = {}
        proactive_prompts = []
        life_area_insight = None
        coaching_insight = None
        emotional_pattern_rows = []
    else:
        profile_row = await get_or_create_profile(db, user)
        profile = profile_snapshot(user, profile_row)
        preferences = await get_or_create_preferences(db, user.id)
        goals = await list_active_goals(db, user.id)
        recent_summary = await summarize_recent_conversations(db, user.id, limit=6)
        relationship_rows = await relationship_context(db, user.id, limit=4)
        due_followups = await list_due_followups(db, user.id, limit=4)
        due_commitments = await list_due_commitments(db, user.id)
        proactive_prompts = await list_proactive_prompts(db, user.id, status="pending")
        if not proactive_prompts:
            generated_prompt = await generate_proactive_prompt(db, user.id)
            if generated_prompt is not None:
                proactive_prompts = [generated_prompt]
        life_area_insight = await recent_life_area_insight(db, user.id)
        coaching_insight = await coaching_context(db, user.id, text)
        emotional_patterns_result = await db.execute(
            select(EmotionalPattern)
            .where(EmotionalPattern.user_id == user.id)
            .order_by(EmotionalPattern.created_at.desc())
            .limit(5)
        )
        emotional_pattern_rows = list(emotional_patterns_result.scalars().all())

    stable_memory = dict((preloaded_context or {}).get("_stable_memory") or {})
    if not stable_memory:
        stable_memory = await memory_manager.retrieve_stable(
            db, user, conversation_id=conv.id
        )
    query_memory = await memory_manager.retrieve_query(db, user.id, text, limit=16)
    retrieved_memory = memory_manager.merge(stable_memory, query_memory)
    goal_tasks: list[str] = []
    task_context: list[dict[str, object]] = []
    if not fast_voice:
        for goal in goals[:3]:
            linked = await task_svc.list_tasks(db, user.id, goal_id=goal.id, top_level_only=True)
            for task in linked[:3]:
                goal_tasks.append(f"{goal.title}: {task.title}")
                task_context.append(
                    {
                        "title": task.title,
                        "status": task.status,
                        "due_at": task.due_at,
                        "goal": goal.title,
                        "created_at": task.created_at,
                        "updated_at": task.updated_at,
                    }
                )

    relationship_lines: list[str] = []
    for memory_type in ("win", "recurring_concern", "important_event", "project", "relationship", "person"):
        for memory in relationship_rows.get(memory_type, [])[:2]:
            relationship_lines.append(f"{memory.type}: {memory.title}")
    followup_lines = [f"{memory.title}: {generate_followup_prompt(memory)}" for memory in due_followups]
    life_area_lines = []
    if life_area_insight is not None:
        life_area_lines.append(f"{life_area_insight['life_area']}: {life_area_insight['text']}")
    coaching_lines: list[str] = []
    if coaching_insight is not None:
        coaching_lines.append(
            f"{coaching_insight['kind']}: {coaching_insight.get('recommendation', '')}"
        )
        if isinstance(coaching_insight.get("analysis"), dict):
            analysis_summary = coaching_insight["analysis"].get("summary")
            if analysis_summary:
                coaching_lines.append(str(analysis_summary))
    preference_lines = [
        f"tone={preferences.tone}",
        f"humor={preferences.humor_level}/5",
        f"directness={preferences.directness_level}/10",
        f"voice_pace={preferences.voice_pace}",
        f"response_length={preferences.response_length}",
    ]
    if preferences.quiet_hours_start and preferences.quiet_hours_end:
        preference_lines.append(f"quiet_hours={preferences.quiet_hours_start}-{preferences.quiet_hours_end}")

    user_message = Message(
        conversation_id=conv.id,
        user_id=user.id,
        role="user",
        content=text,
        emotion=str(emotion["emotion"]),
        intent=mode,
        mode=mode,
        source=source,
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    agenda_action: str | None = None
    direct_agenda_draft_payload: dict[str, Any] | None = None
    agenda_clarification = ambiguous_agenda_request(text)
    reminder_request = extract_reminder_request(text)
    meeting_request = extract_meeting_request(text)
    lower_text = text.lower()
    if agenda_clarification is not None:
        agenda_action = None
    elif reminder_request is not None:
        reminder_title, remind_at = reminder_request
        direct_agenda_draft_payload = _agenda_confirmation_draft(
            kind="reminder",
            title=reminder_title,
            due_at=remind_at,
            source_text=text,
            estimated_minutes=10,
        )
        await draft_svc.save_draft(db, user.id, direct_agenda_draft_payload)
        agenda_action = f"Drafted reminder '{reminder_title}' for {remind_at.isoformat()} and waiting for confirmation."
    elif meeting_request is not None:
        meeting_title, starts_at = meeting_request
        direct_agenda_draft_payload = _agenda_confirmation_draft(
            kind="meeting",
            title=meeting_title,
            due_at=starts_at,
            end_at=starts_at + timedelta(hours=1),
            source_text=text,
            estimated_minutes=60,
        )
        await draft_svc.save_draft(db, user.id, direct_agenda_draft_payload)
        agenda_action = f"Drafted meeting '{meeting_title}' for {starts_at.isoformat()} and waiting for confirmation."
    elif "help me plan tomorrow" in lower_text or "plan tomorrow" in lower_text:
        tomorrow = datetime.combine(local_day, datetime.min.time()).replace(tzinfo=UTC) + timedelta(days=1)
        direct_agenda_draft_payload = {
            "intent": "tomorrow_plan_confirmation",
            "proposed_tasks": [
                {"title": "Morning Review", "due_at": tomorrow.replace(hour=8).isoformat(), "type": "suggested_plan", "priority": 1, "category": "suggested_plan"},
                {"title": "Continue priority project", "due_at": tomorrow.replace(hour=9).isoformat(), "type": "focus", "priority": 1, "category": "focus"},
                {"title": "Follow up on commitments", "due_at": tomorrow.replace(hour=14).isoformat(), "type": "commitment", "priority": 1, "category": "commitment"},
                {"title": "Evening Reflection", "due_at": tomorrow.replace(hour=18).isoformat(), "type": "reflection", "priority": 0, "category": "reflection"},
            ],
            "clarifying_question": None,
        }
        await draft_svc.save_draft(db, user.id, direct_agenda_draft_payload)
        agenda_action = "Drafted a tomorrow agenda with 4 Today items and waiting for confirmation."

    commitment_candidates = await extract_commitments(
        db,
        user.id,
        text,
        source_message_id=user_message.id,
        source_memory_id=None,
    ) if agenda_action is None and agenda_clarification is None else []
    if commitment_candidates:
        commitment_rows = [item for item in commitment_candidates if not item.get("requires_confirmation")]
        if commitment_rows:
            commitment_lines = [
                f"{item['title']}: {item['content']}"
                for item in commitment_rows
            ]
        else:
            commitment_lines = [f"{item['title']}: {item['content']}" for item in commitment_candidates]
    else:
        commitment_lines = []
    commitment_lines.extend(
        f"Due follow-up: {commitment.title}: {generate_commitment_followup(commitment)}"
        for commitment in due_commitments[:3]
    )

    # Keep the existing task planning heuristics available, but only surface
    # draft actions when the message clearly implies planning.
    plan_draft_payload = direct_agenda_draft_payload
    commitment_detected = bool(commitment_candidates)
    if plan_draft_payload is None and agenda_action is None and agenda_clarification is None and not commitment_detected and (mode in {"planner", "assistant"} or plan_extractor.needs_plan_extraction(text)):
        extracted = await plan_extractor.extract_plan(
            text,
            wake_name=user.wake_name or user.display_name or "friend",
            timezone=tz,
            history_summary=recent_context,
            today=local_day,
        )
        if extracted.get("proposed_tasks"):
            await draft_svc.save_draft(db, user.id, extracted)
            plan_draft_payload = extracted
    else:
        extracted = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}

    response_payload = await generate_companion_response(
        user_message=text,
        conversation_history=[
            {"role": line.split(":", 1)[0], "content": line.split(":", 1)[1].strip()}
            for line in recent_context.splitlines()
            if ":" in line
        ],
        tasks=retrieved_memory["tasks"] + task_context,
        memories=retrieved_memory["memories"],
        goals=retrieved_memory["goals"],
        commitments=[
            {
                "id": str(commitment.id),
                "title": commitment.title,
                "content": commitment.content,
                "status": commitment.status,
                "due_at": commitment.due_at,
                "follow_up_at": commitment.follow_up_at,
                "follow_up_prompt": generate_commitment_followup(commitment),
                "confidence": commitment.confidence,
                "related_entity_name": commitment.related_entity_name,
            }
            for commitment in due_commitments
        ]
        + [item for item in commitment_candidates if isinstance(item, dict)],
        projects=retrieved_memory["projects"],
        people=retrieved_memory["people"],
        emotional_patterns=[
            {
                "id": str(pattern.id),
                "pattern_type": pattern.pattern_type,
                "emotion": pattern.emotion,
                "life_area": pattern.life_area,
                "summary": pattern.summary,
                "confidence": pattern.confidence,
                "created_at": pattern.created_at,
            }
            for pattern in emotional_pattern_rows
        ],
        user_preferences={
            "wake_name": user.wake_name or user.display_name or "friend",
            "profile_summary": profile.get("summary") or "",
            "recent_summary": recent_summary,
            "relationship_context": "\n".join(relationship_lines),
            "due_followups": "\n".join(followup_lines),
            "life_area_balance": "\n".join(life_area_lines),
            "coaching_context": "\n".join(coaching_lines),
            "completed_action": agenda_action or "",
            "clarifying_action": agenda_clarification or "",
            "tone": preferences.tone,
            "humor_level": preferences.humor_level,
            "directness_level": preferences.directness_level,
            "voice_pace": preferences.voice_pace,
            "response_length": preferences.response_length,
        },
        output_channel=source,
    )
    reply = _clean_user_facing_reply(str(response_payload["reply"]))
    if not reply:
        reply = "I hear you. Say that one more time in your own words, and I’ll stay with the thread."

    suggested_actions = _suggested_actions_for(
        mode,
        plan_draft_payload,
        text,
        commitment_detected=commitment_detected,
    )
    life_area_action = _life_area_suggestion(life_area_insight)
    if life_area_action is not None and mode in {"companion", "coach", "reflection"}:
        suggested_actions.insert(0, life_area_action)
    if coaching_insight is not None:
        kind = str(coaching_insight.get("kind") or "")
        if kind == "decision":
            suggested_actions.insert(
                0,
                {
                    "type": "review_decision",
                    "label": "Review decision analysis",
                    "description": str(coaching_insight.get("recommendation") or "Review the decision tradeoffs."),
                    "requires_confirmation": False,
                },
            )
        elif kind == "growth_plan":
            suggested_actions.insert(
                0,
                {
                    "type": "create_growth_plan",
                    "label": "Create a growth plan",
                    "description": str(coaching_insight.get("recommendation") or "Create a 30/60/90-day growth plan."),
                    "requires_confirmation": True,
                },
            )
        elif kind == "accountability":
            suggested_actions.insert(
                0,
                {
                    "type": "accountability_checkin",
                    "label": "Accountability check-in",
                    "description": str(coaching_insight.get("recommendation") or "Talk through what got in the way."),
                    "requires_confirmation": False,
                },
            )
        elif kind == "habit":
            suggested_actions.insert(
                0,
                {
                    "type": "track_habit",
                    "label": "Track as a habit",
                    "description": str(coaching_insight.get("recommendation") or "Ask permission before tracking this habit."),
                    "requires_confirmation": True,
                },
            )
    if due_commitments and _should_surface_commitments(text, mode, str(emotion["emotion"]), due_commitments):
        for commitment in due_commitments[:3]:
            suggested_actions.insert(
                0,
                {
                    "type": "commitment_follow_up",
                    "label": generate_commitment_followup(commitment),
                    "description": f"Check in on {commitment.title}.",
                    "requires_confirmation": False,
                },
            )
    if _should_surface_followups(text, mode, str(emotion["emotion"]), due_followups):
        for memory in due_followups[:3]:
            suggested_actions.insert(
                0,
                {
                    "type": "follow_up",
                    "label": generate_followup_prompt(memory),
                    "description": f"Follow up on {memory.title}.",
                    "requires_confirmation": False,
                },
            )
    if proactive_prompts and mode in {"companion", "reflection"} and len(text.split()) <= 6:
        suggested_actions.insert(
            0,
            {
                "type": "proactive_prompt",
                "label": "Gentle check-in available",
                "description": f"Structured trigger: {proactive_prompts[0].trigger_type}",
                "requires_confirmation": False,
            },
        )
    memory_candidates = extract_memories_from_message(text, emotion=str(emotion["emotion"]), mode=mode)
    sensitive_candidates = [candidate for candidate in memory_candidates if candidate.get("sensitive")]
    confirmation_candidates = [candidate for candidate in memory_candidates if candidate.get("requires_confirmation")]
    commitment_confirmation = next((item for item in commitment_candidates if item.get("requires_confirmation")), None)
    requires_confirmation = bool(
        plan_draft_payload and plan_draft_payload.get("proposed_tasks")
    ) or bool(sensitive_candidates) or bool(confirmation_candidates)
    requires_confirmation = requires_confirmation or commitment_confirmation is not None
    confirmation_prompt = None
    if commitment_confirmation is not None:
        title = str(commitment_confirmation.get("title") or "that")
        confirmation_prompt = f"That sounds like something you may want me to remember. Should I track {title.lower()} as a commitment?"
    elif plan_draft_payload and plan_draft_payload.get("proposed_tasks"):
        intent = str(plan_draft_payload.get("intent") or "")
        proposed = plan_draft_payload.get("proposed_tasks") or []
        first = proposed[0] if proposed else {}
        title = str(first.get("title") or "this")
        due_at = str(first.get("due_at") or "")
        if "reminder" in intent:
            confirmation_prompt = f"I've got a reminder: {title}{f' at {due_at}' if due_at else ''}. Should I save it to Today?"
        elif "meeting" in intent:
            confirmation_prompt = f"I've got a meeting: {title}{f' at {due_at}' if due_at else ''}. Should I save it to Today?"
        else:
            confirmation_prompt = "I drafted a plan for you. Should I add those items to Today?"
    elif sensitive_candidates:
        confirmation_prompt = "This seems personal. Should I remember it?"
    elif confirmation_candidates:
        confirmation_prompt = "I think this is worth remembering, but I want to make sure before I save it. Should I keep it?"

    assistant_message = Message(
        conversation_id=conv.id,
        user_id=user.id,
        role="assistant",
        content=reply,
        emotion=None,
        intent=mode,
        mode=mode,
        source=source,
    )
    db.add(assistant_message)
    conv.mode = mode
    if not conv.title:
        conv.title = _conversation_title(text)
    await db.commit()
    await db.refresh(assistant_message)
    await memory_manager.index_row(db, user_message)
    await memory_manager.index_row(db, assistant_message)
    await conv_svc.append_turn(db, user.id, str(conv.id), "user", text)
    await conv_svc.append_turn(db, user.id, str(conv.id), "assistant", reply)
    await _refresh_recent_context_cache(db, user.id, conv.id)

    if not source.startswith("brain_"):
        await persist_extracted_memories(
            db,
            user.id,
            user_message.id,
            text,
            emotion=str(emotion["emotion"]),
            mode=mode,
        )

    if commitment_candidates and not commitment_confirmation:
        await record_audit(
            db,
            user.id,
            "commitment.detected",
            "commitment",
            str(user_message.id),
            {"count": len(commitment_candidates)},
        )

    mem_used = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "type": item.get("type") or item.get("source_type"),
            "life_area": item.get("life_area"),
        }
        for item in retrieved_memory["memories"][:8]
    ]

    return {
        "reply": reply,
        "mode": mode,
        "emotion": emotion,
        "memories_used": mem_used,
        "suggested_actions": suggested_actions,
        "plan_draft": draft_to_schema(plan_draft_payload),
        "requires_confirmation": requires_confirmation,
        "confirmation_prompt": confirmation_prompt,
        "commitments": commitment_candidates,
        "conversation_id": conv.id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
        "memory_metrics": retrieved_memory["metrics"],
    }


class CompanionOrchestrator:
    async def run_turn(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        *,
        conversation_id: uuid.UUID | None = None,
        source: str = "text",
        source_context: dict[str, Any] | None = None,
    ) -> dict[str, object]:
        terminal: dict[str, Any] | None = None
        internal_context = source_context or {}
        async for event in self.run_turn_stream(
            db,
            user,
            message,
            conversation_id=conversation_id,
            source=source,
            source_context=source_context,
            preloaded_context=dict(internal_context.get("preloaded_context") or {}),
            cancel_event=internal_context.get("_cancel_event"),
        ):
            if event.get("type") == "turn_complete":
                terminal = {key: value for key, value in event.items() if key != "type"}
        if terminal is None:
            raise RuntimeError("Conversation stream completed without a terminal event")
        return terminal

    async def run_turn_stream(
        self,
        db: AsyncSession,
        user: User,
        message: str,
        *,
        conversation_id: uuid.UUID | None = None,
        source: str = "voice",
        source_context: dict[str, Any] | None = None,
        preloaded_context: dict[str, Any] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run every modality through one event-producing conversation brain."""
        text = sanitize_untrusted_text((message or "").strip())
        internal_context = dict(source_context or {})
        internal_context.setdefault("source", source)
        if preloaded_context:
            internal_context["preloaded_context"] = preloaded_context
        if cancel_event is not None:
            internal_context["_cancel_event"] = cancel_event
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError

        routed = await execute_companion_tool(
            db,
            user,
            text,
            source_context=internal_context,
        )
        if routed is not None:
            payload = _default_turn_result(routed)
            reply = str(payload.get("reply") or "")
            yield {
                "type": "context_ready",
                "mode": payload.get("mode", "assistant"),
                "emotion": payload.get("emotion"),
                "metrics": {"explicit_tool": True},
            }
            if reply:
                yield {"type": "reply_delta", "text": reply}
                yield {"type": "speech_segment_ready", "text": reply}
            yield {"type": "turn_complete", **payload}
            return

        reasoning_fallback_reason: str | None = None
        runtime_settings = get_settings()
        if runtime_settings.ai_reasoning_enabled and text and is_safe_message(text):
            if runtime_settings.ai_streaming_enabled:
                async for event in stream_reasoned_turn(
                    db,
                    user,
                    text,
                    conversation_id=conversation_id,
                    source=source,
                    source_context=internal_context,
                    preloaded_context=preloaded_context,
                    cancel_event=cancel_event,
                ):
                    if event.get("type") == "stream_fallback_required":
                        reasoning_fallback_reason = str(
                            event.get("reason") or "reasoning_failed"
                        )
                        break
                    yield event
            else:
                attempt = await try_run_reasoned_turn(
                    db,
                    user,
                    text,
                    conversation_id=conversation_id,
                    source=source,
                    source_context=internal_context,
                    preloaded_context=preloaded_context,
                    cancel_event=cancel_event,
                )
                if attempt.result is not None:
                    reply = str(attempt.result.get("reply") or "")
                    yield {
                        "type": "context_ready",
                        "mode": attempt.result.get("mode", "companion"),
                        "emotion": attempt.result.get("emotion"),
                        "metrics": {"streaming_rollout_fallback": True},
                    }
                    if reply:
                        yield {"type": "reply_delta", "text": reply}
                        yield {"type": "speech_segment_ready", "text": reply}
                    yield {"type": "turn_complete", **attempt.result}
                    return
                reasoning_fallback_reason = attempt.fallback_reason
            if reasoning_fallback_reason is None:
                return

        contextual = await _handle_source_context_action(
            db,
            user,
            text,
            conversation_id=conversation_id,
            source=source,
            source_context=internal_context,
        )
        if contextual is not None:
            result = _default_turn_result(contextual)
        else:
            result = await _run_turn_impl(
                db,
                user,
                text,
                conversation_id=conversation_id,
                source=source,
                preloaded_context=preloaded_context,
            )
        if reasoning_fallback_reason:
            metrics = dict(result.get("reasoning_metrics") or {})
            metrics.update(
                {
                    "used_compatibility_fallback": True,
                    "fallback_reason": reasoning_fallback_reason,
                }
            )
            result["reasoning_metrics"] = metrics
        reply = str(result.get("reply") or "")
        yield {
            "type": "context_ready",
            "mode": result.get("mode", "companion"),
            "emotion": result.get("emotion"),
            "metrics": {"buffered_safety_fallback": True},
        }
        if reply:
            yield {"type": "reply_delta", "text": reply}
            yield {"type": "speech_segment_ready", "text": reply}
        yield {"type": "turn_complete", **result}

_ORCHESTRATOR = CompanionOrchestrator()


def get_companion_orchestrator() -> CompanionOrchestrator:
    return _ORCHESTRATOR


async def run_turn(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None = None,
    source: str = "text",
    source_context: dict[str, Any] | None = None,
) -> dict[str, object]:
    return await get_companion_orchestrator().run_turn(
        db,
        user,
        message,
        conversation_id=conversation_id,
        source=source,
        source_context=source_context,
    )


async def run_turn_stream(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    conversation_id: uuid.UUID | None = None,
    source: str = "voice",
    source_context: dict[str, Any] | None = None,
    preloaded_context: dict[str, Any] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for event in get_companion_orchestrator().run_turn_stream(
        db,
        user,
        message,
        conversation_id=conversation_id,
        source=source,
        source_context=source_context,
        preloaded_context=preloaded_context,
        cancel_event=cancel_event,
    ):
        yield event


async def _get_or_create_conversation(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    mode: str,
    message: str,
) -> Conversation:
    if conversation_id is not None:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
    conversation = Conversation(
        id=conversation_id or uuid.uuid4(),
        user_id=user_id,
        mode=mode,
        title=_conversation_title(message),
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def _recent_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    limit: int = 6,
) -> str:
    if conversation_id is None:
        return ""
    cached = await get_context_cache(str(user_id), str(conversation_id))
    if cached and isinstance(cached.get("recent_context"), str):
        return str(cached["recent_context"])
    return await _refresh_recent_context_cache(db, user_id, conversation_id, limit=limit)


async def _refresh_recent_context_cache(
    db: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 6,
) -> str:
    result = await db.execute(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == user_id, Conversation.id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    recent_context = "\n".join(f"{row.role}: {row.content[:160]}" for row in rows)
    await set_context_cache(
        str(user_id),
        str(conversation_id),
        {
            "recent_context": recent_context,
            "message_count": len(rows),
        },
    )
    return recent_context


async def _store_simple_turn(
    db: AsyncSession,
    conversation: Conversation,
    user_id: uuid.UUID,
    user_text: str,
    reply: str,
    *,
    source: str,
    mode: str,
) -> dict[str, object]:
    emotion = detect_emotion(user_text)
    user_message = Message(
        conversation_id=conversation.id,
        user_id=user_id,
        role="user",
        content=user_text,
        emotion=str(emotion["emotion"]),
        intent=mode,
        mode=mode,
        source=source,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=user_id,
        role="assistant",
        content=reply,
        emotion=None,
        intent=mode,
        mode=mode,
        source=source,
    )
    db.add(user_message)
    db.add(assistant_message)
    await db.commit()
    await db.refresh(user_message)
    await db.refresh(assistant_message)
    await memory_manager.index_row(db, user_message)
    await memory_manager.index_row(db, assistant_message)
    await conv_svc.append_turn(db, user_id, str(conversation.id), "user", user_text)
    await conv_svc.append_turn(db, user_id, str(conversation.id), "assistant", reply)
    await _refresh_recent_context_cache(db, user_id, conversation.id)
    return {
        "reply": reply,
        "mode": mode,
        "emotion": emotion,
        "memories_used": [],
        "suggested_actions": [],
        "plan_draft": None,
        "requires_confirmation": False,
        "confirmation_prompt": None,
        "conversation_id": conversation.id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant_message.id,
    }


def _history_from_recent_context(recent_context: str) -> list[dict[str, str]]:
    return [
        {"role": line.split(":", 1)[0], "content": line.split(":", 1)[1].strip()}
        for line in recent_context.splitlines()
        if ":" in line
    ]


async def preload_turn_context(
    db: AsyncSession,
    user: User,
    *,
    conversation_id: uuid.UUID | None,
    partial_message: str = "",
) -> dict[str, Any]:
    """Preload reusable turn context while voice STT is still finalizing."""
    started = time.monotonic()
    cached = await get_context_cache(str(user.id), str(conversation_id or "new"))
    cache_hit = bool(cached and cached.get("stream_context"))
    if cache_hit:
        payload = dict(cached["stream_context"])
        stable_memory = await memory_manager.retrieve_stable(
            db, user, conversation_id=conversation_id
        )
        stable_merged = memory_manager.merge(stable_memory, {"items": [], "metrics": {}})
        payload["tasks"] = stable_merged["tasks"]
        payload["memories"] = stable_merged["memories"]
        payload["goals"] = stable_merged["goals"]
        payload["projects"] = stable_merged["projects"]
        payload["people"] = stable_merged["people"]
        payload["_stable_memory"] = stable_memory
        preferences = await get_or_create_preferences(db, user.id)
        user_preferences = dict(payload.get("user_preferences") or {})
        user_preferences["voice_profile"] = preferences.tts_voice
        user_preferences["tts_voice"] = preferences.tts_voice
        user_preferences.setdefault("voice_pace", preferences.voice_pace)
        payload["user_preferences"] = user_preferences
        payload["context_cache_hit"] = True
        payload["context_ready_ms"] = int((time.monotonic() - started) * 1000)
        return payload

    stable_memory = await memory_manager.retrieve_stable(
        db, user, conversation_id=conversation_id
    )
    recent_context = await _recent_context(db, user.id, conversation_id)
    # Keep the same AsyncSession safe: preload starts early, so this can run
    # before final STT without racing one session across concurrent queries.
    preferences = await get_or_create_preferences(db, user.id)
    due_followups = await list_due_followups(db, user.id, limit=4)
    due_commitments = await list_due_commitments(db, user.id)
    recent_summary = await summarize_recent_conversations(db, user.id, limit=6)
    relationship_rows = await relationship_context(db, user.id, limit=4)
    life_area_insight = await recent_life_area_insight(db, user.id)
    emotional_patterns_result = await db.execute(
        select(EmotionalPattern)
        .where(EmotionalPattern.user_id == user.id)
        .order_by(EmotionalPattern.created_at.desc())
        .limit(5)
    )
    relationship_lines: list[str] = []
    for memory_type in ("win", "recurring_concern", "important_event", "project", "relationship", "person"):
        for memory in relationship_rows.get(memory_type, [])[:2]:
            relationship_lines.append(f"{memory.type}: {memory.title}")
    followup_lines = [f"{memory.title}: {generate_followup_prompt(memory)}" for memory in due_followups]
    life_area_lines = []
    if life_area_insight is not None:
        life_area_lines.append(f"{life_area_insight['life_area']}: {life_area_insight['text']}")

    payload: dict[str, Any] = {
        "conversation_history": _history_from_recent_context(recent_context),
        "tasks": stable_memory["tasks"] + stable_memory["today"] + stable_memory["calendar"] + stable_memory["reminders"],
        "memories": stable_memory["long_term_memory"] + stable_memory["recent_discussions"],
        "goals": stable_memory["goals"],
        "commitments": [
            {
                "id": str(commitment.id),
                "title": commitment.title,
                "content": commitment.content,
                "status": commitment.status,
                "due_at": commitment.due_at,
                "follow_up_at": commitment.follow_up_at,
                "follow_up_prompt": generate_commitment_followup(commitment),
                "confidence": commitment.confidence,
                "related_entity_name": commitment.related_entity_name,
            }
            for commitment in due_commitments
        ],
        "projects": stable_memory["projects"],
        "people": stable_memory["people"],
        "emotional_patterns": [
            {
                "id": str(pattern.id),
                "pattern_type": pattern.pattern_type,
                "emotion": pattern.emotion,
                "life_area": pattern.life_area,
                "summary": pattern.summary,
                "confidence": pattern.confidence,
                "created_at": pattern.created_at,
            }
            for pattern in emotional_patterns_result.scalars().all()
        ],
        "user_preferences": {
            "wake_name": user.wake_name or user.display_name or "friend",
            "profile_summary": user.about_me or "",
            "recent_summary": recent_summary,
            "relationship_context": "\n".join(relationship_lines),
            "due_followups": "\n".join(followup_lines),
            "life_area_balance": "\n".join(life_area_lines),
            "tone": preferences.tone,
            "humor_level": preferences.humor_level,
            "directness_level": preferences.directness_level,
            "voice_pace": preferences.voice_pace,
            "voice_profile": preferences.tts_voice,
            "tts_voice": preferences.tts_voice,
            "response_length": preferences.response_length,
        },
        "context_cache_hit": False,
        "context_ready_ms": int((time.monotonic() - started) * 1000),
        "_stable_memory": stable_memory,
    }
    await set_context_cache(
        str(user.id),
        str(conversation_id or "new"),
        {"stream_context": payload, "recent_context": recent_context},
    )
    return payload
