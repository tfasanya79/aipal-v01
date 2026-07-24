"""Voice Conversation Manager between STT and the Companion Brain.

This layer owns transcript reliability, short-lived field collection, and
confirmation-before-save for voice turns. It deliberately does not replace the
CompanionOrchestrator; it decides whether a voice transcript is safe/complete
enough to reach the Brain, or whether AiPal should ask a direct follow-up first.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..models import User
from ..timezone_util import user_local_today
from . import plan_draft as draft_svc
from . import plan_intent
from .conversation_state_manager import get_voice_session_state, update_voice_session_state
from .today_item_service import parse_action_datetime
from .tool_registry import ToolExecutionContext, tool_registry

log = logging.getLogger("aipal.conversation_manager")

ConversationManagerAction = Literal["proceed", "direct_reply"]


@dataclass(slots=True)
class ConversationManagerResult:
    action: ConversationManagerAction
    transcript: str
    reply: str | None = None
    state: str = "thinking"
    intent: str = "general_conversation"
    plan_draft: dict[str, Any] | None = None
    draft_confirmed: bool = False
    requires_confirmation: bool = False
    confirmation_prompt: str | None = None
    suggested_actions: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None


class ConversationManager:
    """Control layer for voice transcripts before LLM generation."""

    async def handle_partial_transcript(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        turn_id: str,
        text: str,
        confidence: float | None = None,
    ) -> None:
        await update_voice_session_state(
            str(user_id),
            str(session_id),
            last_state="listening",
            current_turn_id=turn_id,
            partial_transcript=text,
            partial_confidence=confidence,
        )

    async def handle_interrupt(
        self,
        *,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        turn_id: str | None,
    ) -> None:
        await update_voice_session_state(
            str(user_id),
            str(session_id),
            last_state="interrupted",
            interrupted_turn_id=turn_id,
            currently_speaking="user",
        )
        log.info("voice_interrupted user=%s session=%s turn=%s", user_id, session_id, turn_id)

    async def handle_final_transcript(
        self,
        db: AsyncSession,
        user: User,
        *,
        session_id: uuid.UUID,
        turn_id: str,
        transcript: str,
        confidence: float | None,
        language: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> ConversationManagerResult:
        text = " ".join((transcript or "").split())
        metrics = dict(metrics or {})
        confidence = float(confidence if confidence is not None else metrics.get("stt_confidence", 1.0) or 0.0)

        await update_voice_session_state(
            str(user.id),
            str(session_id),
            last_state="thinking",
            current_turn_id=turn_id,
            final_transcript=text,
            final_confidence=confidence,
            language=language or metrics.get("stt_language"),
        )
        log.info(
            "voice_transcript_final user=%s session=%s turn=%s confidence=%.3f text=%r",
            user.id,
            session_id,
            turn_id,
            confidence,
            text[:240],
        )

        if not self._transcript_reliable(text, confidence, metrics):
            return await self._direct_reply(
                user,
                session_id,
                text,
                reply="Sorry, I didn't catch that clearly. Could you say it again?",
                state="listening",
                intent="low_confidence_transcript",
                metrics={**metrics, "conversation_manager": "low_confidence"},
            )

        state = await get_voice_session_state(str(user.id), str(session_id))
        pending = state.get("pending_action") if isinstance(state.get("pending_action"), dict) else None

        if pending:
            pending_state = str(pending.get("state") or "")
            if pending_state == "awaiting_confirmation":
                return await self.confirm_pending_action(db, user, session_id=session_id, transcript=text, pending=pending, metrics=metrics)
            if pending_state in {"collecting_task_fields", "collecting_reminder_fields", "collecting_meeting_fields"}:
                return await self._continue_field_collection(db, user, session_id=session_id, transcript=text, pending=pending, metrics=metrics)

        intent = self.detect_intent(text)
        if intent == "schedule_meeting":
            return await self._start_meeting_flow(db, user, session_id=session_id, transcript=text, metrics=metrics)
        if intent in {"create_reminder", "create_task"}:
            return await self._start_task_flow(db, user, session_id=session_id, transcript=text, intent=intent, metrics=metrics)
        if intent in {"ask_today", "ask_upcoming_agenda", "update_memory", "general_conversation"}:
            await update_voice_session_state(
                str(user.id),
                str(session_id),
                last_state="thinking",
                current_intent=intent,
                pending_action=None,
            )
            return ConversationManagerResult(action="proceed", transcript=text, intent=intent, metrics=metrics)

        return ConversationManagerResult(action="proceed", transcript=text, intent="general_conversation", metrics=metrics)

    def detect_intent(self, text: str) -> str:
        lower = text.lower().strip()
        if re.search(r"\b(what do i have|what's on|what is on|agenda|schedule)\b", lower) and re.search(r"\b(today|this morning|this afternoon)\b", lower):
            return "ask_today"
        if re.search(r"\b(upcoming|next|tomorrow|week)\b", lower) and "agenda" in lower:
            return "ask_upcoming_agenda"
        if re.search(r"\b(remember that|remember i|keep in mind|note that)\b", lower):
            return "update_memory"
        if re.search(r"\b(move|reschedule)\b.*\b(meeting|call|appointment)\b", lower):
            return "reschedule_meeting"
        if re.search(r"\b(cancel)\b.*\b(meeting|call|appointment)\b", lower):
            return "cancel_meeting"
        if re.search(r"\b(cancel|delete|remove)\b.*\b(task|reminder|todo)\b", lower):
            return "cancel_task"
        if re.search(r"\b(meeting|appointment|call)\b", lower) and re.search(r"\b(schedule|book|set up|have|meeting with|meet with)\b", lower):
            return "schedule_meeting"
        if lower.startswith("remind me") or re.search(r"\breminder\b", lower):
            return "create_reminder"
        if re.search(r"\b(add|create|track|need to|i need to|todo|task)\b", lower):
            return "create_task"
        return "general_conversation"

    async def build_llm_context(self, db: AsyncSession, user: User, session_id: uuid.UUID) -> dict[str, Any]:
        """Small structured context summary for diagnostics/future providers.

        The CompanionOrchestrator still builds the full narrative prompt.
        """
        state = await get_voice_session_state(str(user.id), str(session_id))
        draft = await draft_svc.get_draft(db, user.id)
        return {
            "session_id": str(session_id),
            "timezone": user.timezone or "UTC",
            "current_date": user_local_today(user.timezone or "UTC").isoformat(),
            "pending_action": state.get("pending_action"),
            "plan_draft": draft,
        }

    async def process_llm_response(self, *args: Any, **kwargs: Any) -> None:
        """Reserved extension point: post-response policy stays backend-owned."""
        return None

    async def execute_action(self, db: AsyncSession, user: User, *, timezone: str | None = None) -> list[dict[str, Any]]:
        result = await tool_registry.execute(
            ToolExecutionContext(
                db=db,
                user=user,
                message="Confirm the pending planner draft.",
                source="voice",
                source_context={"tool": "planner_engine", "action": "confirm_draft", "timezone": timezone},
            ),
            "planner_engine",
            {"action": "confirm_draft"},
        )
        return list((result.tool_result or {}).get("created") or [])

    async def confirm_pending_action(
        self,
        db: AsyncSession,
        user: User,
        *,
        session_id: uuid.UUID,
        transcript: str,
        pending: dict[str, Any],
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        if plan_intent.is_confirm_intent(transcript):
            created = await self.execute_action(db, user)
            await update_voice_session_state(
                str(user.id),
                str(session_id),
                last_state="action_completed",
                pending_action=None,
            )
            label = self._created_label(created)
            return ConversationManagerResult(
                action="direct_reply",
                transcript=transcript,
                reply=f"Done. I’ve added {label} to Today.",
                state="action_completed",
                intent=str(pending.get("intent") or "confirm_pending_action"),
                draft_confirmed=True,
                requires_confirmation=False,
                suggested_actions=[{"type": "draft_confirmed", "label": "Added to Today", "requires_confirmation": False}],
                metrics={**metrics, "conversation_manager": "confirmed_action", "created_count": len(created)},
            )
        if plan_intent.is_discard_intent(transcript):
            await draft_svc.clear_draft(db, user.id)
            await update_voice_session_state(
                str(user.id),
                str(session_id),
                last_state="listening",
                pending_action=None,
            )
            return ConversationManagerResult(
                action="direct_reply",
                transcript=transcript,
                reply="No problem. I won’t save it.",
                state="listening",
                intent="reject_pending_action",
                metrics={**metrics, "conversation_manager": "rejected_action"},
            )
        return ConversationManagerResult(
            action="direct_reply",
            transcript=transcript,
            reply="Should I save it to Today?",
            state="awaiting_confirmation",
            intent=str(pending.get("intent") or "awaiting_confirmation"),
            plan_draft=await draft_svc.get_draft(db, user.id),
            requires_confirmation=True,
            confirmation_prompt="Should I save it to Today?",
            metrics={**metrics, "conversation_manager": "confirmation_unclear"},
        )

    async def _start_meeting_flow(
        self,
        db: AsyncSession,
        user: User,
        *,
        session_id: uuid.UUID,
        transcript: str,
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        fields = self._extract_meeting_fields(transcript, base={})
        missing = self._missing_meeting_fields(fields)
        if missing:
            return await self._ask_for_missing_field(user, session_id, transcript, fields, "meeting", missing[0], metrics)
        return await self._save_confirmation_draft(db, user, session_id, transcript, "meeting", fields, metrics)

    async def _start_task_flow(
        self,
        db: AsyncSession,
        user: User,
        *,
        session_id: uuid.UUID,
        transcript: str,
        intent: str,
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        fields = self._extract_task_fields(transcript, base={}, item_type="reminder" if intent == "create_reminder" else "task")
        missing = self._missing_task_fields(fields)
        if missing:
            return await self._ask_for_missing_field(user, session_id, transcript, fields, fields.get("type", "task"), missing[0], metrics)
        return await self._save_confirmation_draft(db, user, session_id, transcript, str(fields.get("type") or "task"), fields, metrics)

    async def _continue_field_collection(
        self,
        db: AsyncSession,
        user: User,
        *,
        session_id: uuid.UUID,
        transcript: str,
        pending: dict[str, Any],
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        kind = str(pending.get("kind") or "task")
        fields = dict(pending.get("fields") or {})
        if kind == "meeting":
            fields = self._extract_meeting_fields(transcript, base=fields)
            missing = self._missing_meeting_fields(fields)
        else:
            fields = self._extract_task_fields(transcript, base=fields, item_type=kind)
            missing = self._missing_task_fields(fields)
        if missing:
            return await self._ask_for_missing_field(user, session_id, transcript, fields, kind, missing[0], metrics)
        return await self._save_confirmation_draft(db, user, session_id, transcript, kind, fields, metrics)

    async def _ask_for_missing_field(
        self,
        user: User,
        session_id: uuid.UUID,
        transcript: str,
        fields: dict[str, Any],
        kind: str,
        field: str,
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        state = "collecting_meeting_fields" if kind == "meeting" else "collecting_task_fields"
        reply = self._question_for(kind, field)
        await update_voice_session_state(
            str(user.id),
            str(session_id),
            last_state=state,
            pending_action={"state": state, "kind": kind, "intent": f"{kind}_field_collection", "fields": fields, "missing": field},
        )
        log.info("voice_missing_field user=%s session=%s kind=%s field=%s fields=%s", user.id, session_id, kind, field, fields)
        return ConversationManagerResult(
            action="direct_reply",
            transcript=transcript,
            reply=reply,
            state=state,
            intent=f"collecting_{kind}_fields",
            metrics={**metrics, "conversation_manager": "missing_field", "missing_field": field},
        )

    async def _save_confirmation_draft(
        self,
        db: AsyncSession,
        user: User,
        session_id: uuid.UUID,
        transcript: str,
        kind: str,
        fields: dict[str, Any],
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        draft = self._draft_payload(kind, fields, transcript)
        await draft_svc.save_draft(db, user.id, draft)
        summary = self._confirmation_summary(kind, fields)
        await update_voice_session_state(
            str(user.id),
            str(session_id),
            last_state="awaiting_confirmation",
            pending_action={"state": "awaiting_confirmation", "kind": kind, "intent": draft["intent"], "fields": fields},
        )
        return ConversationManagerResult(
            action="direct_reply",
            transcript=transcript,
            reply=summary,
            state="awaiting_confirmation",
            intent=str(draft["intent"]),
            plan_draft=draft,
            requires_confirmation=True,
            confirmation_prompt="Should I save it to Today?",
            suggested_actions=[{"type": "confirm_draft", "label": "Save to Today", "requires_confirmation": True}],
            metrics={**metrics, "conversation_manager": "awaiting_confirmation"},
        )

    async def _direct_reply(
        self,
        user: User,
        session_id: uuid.UUID,
        transcript: str,
        *,
        reply: str,
        state: str,
        intent: str,
        metrics: dict[str, Any],
    ) -> ConversationManagerResult:
        await update_voice_session_state(
            str(user.id),
            str(session_id),
            last_state=state,
        )
        return ConversationManagerResult(
            action="direct_reply",
            transcript=transcript,
            reply=reply,
            state=state,
            intent=intent,
            metrics=metrics,
        )

    def _transcript_reliable(self, text: str, confidence: float, metrics: dict[str, Any]) -> bool:
        settings = get_settings()
        if len(text) < settings.stt_min_final_chars:
            return False
        no_speech = float(metrics.get("stt_no_speech_probability", 0.0) or 0.0)
        return confidence >= settings.stt_min_confidence and no_speech <= settings.stt_max_no_speech_probability

    def _extract_meeting_fields(self, text: str, *, base: dict[str, Any]) -> dict[str, Any]:
        fields = dict(base)
        lower = text.lower()
        if not fields.get("title"):
            person = self._person_after_with(text) or self._person_after_meet(text)
            fields["title"] = f"Meeting with {person}" if person else self._clean_title(text, fallback="Meeting")
            if person:
                fields.setdefault("participants", [person])
        when = parse_action_datetime(text)
        date_hint = self._date_hint(text)
        time_hint = self._time_hint(text)
        if when is not None and ("date" not in fields or time_hint):
            fields["date"] = when.date().isoformat()
            if time_hint or re.search(r"\b(at|by)\s+\d", lower):
                fields["start_time"] = when.isoformat()
        elif date_hint and not fields.get("date"):
            fields["date"] = date_hint.isoformat()
        if time_hint and fields.get("date") and not fields.get("start_time"):
            day = date.fromisoformat(str(fields["date"]))
            fields["start_time"] = datetime.combine(day, time(time_hint[0], time_hint[1]), tzinfo=UTC).isoformat()
        duration = self._duration_minutes(text)
        if duration:
            fields["duration_minutes"] = duration
        location = self._location_hint(text)
        if location:
            fields["location"] = location
        return fields

    def _extract_task_fields(self, text: str, *, base: dict[str, Any], item_type: str) -> dict[str, Any]:
        fields = dict(base)
        fields["type"] = fields.get("type") or item_type
        if not fields.get("title"):
            fields["title"] = self._task_title(text, item_type=item_type)
        when = parse_action_datetime(text)
        date_hint = self._date_hint(text)
        time_hint = self._time_hint(text)
        if when is not None:
            fields["due_at"] = when.isoformat()
        elif date_hint and time_hint:
            fields["due_at"] = datetime.combine(date_hint, time(time_hint[0], time_hint[1]), tzinfo=UTC).isoformat()
        elif date_hint:
            fields["date"] = date_hint.isoformat()
        if "urgent" in text.lower() or "important" in text.lower():
            fields["priority"] = 2
        return fields

    def _missing_meeting_fields(self, fields: dict[str, Any]) -> list[str]:
        missing = []
        if not fields.get("title"):
            missing.append("title")
        if not fields.get("date"):
            missing.append("date")
        if not fields.get("start_time"):
            missing.append("start_time")
        if not fields.get("duration_minutes"):
            missing.append("duration")
        return missing

    def _missing_task_fields(self, fields: dict[str, Any]) -> list[str]:
        missing = []
        if not fields.get("title"):
            missing.append("title")
        if not fields.get("due_at") and not fields.get("date"):
            missing.append("date")
        return missing

    def _draft_payload(self, kind: str, fields: dict[str, Any], transcript: str) -> dict[str, Any]:
        due_at = fields.get("start_time") or fields.get("due_at")
        if not due_at and fields.get("date"):
            due_at = datetime.combine(date.fromisoformat(str(fields["date"])), time(9, 0), tzinfo=UTC).isoformat()
        item: dict[str, Any] = {
            "type": kind,
            "title": fields.get("title") or kind.title(),
            "notes": transcript,
            "due_at": due_at,
            "estimated_minutes": int(fields.get("duration_minutes") or (60 if kind == "meeting" else 30)),
            "priority": int(fields.get("priority") or 1),
            "category": kind,
        }
        if kind == "meeting":
            start = self._parse_dt(str(due_at)) if due_at else None
            duration = int(fields.get("duration_minutes") or 60)
            item["start_time"] = due_at
            item["end_time"] = (start + timedelta(minutes=duration)).isoformat() if start else None
            item["location"] = fields.get("location")
            item["participants"] = fields.get("participants")
        return {"intent": f"{kind}_confirmation", "proposed_tasks": [item], "clarifying_question": None}

    def _confirmation_summary(self, kind: str, fields: dict[str, Any]) -> str:
        if kind == "meeting":
            return (
                "Got it. Here’s what I have:\n\n"
                f"Meeting: {fields.get('title', 'Meeting')}\n"
                f"Date: {fields.get('date', 'Not specified')}\n"
                f"Time: {self._format_time(fields.get('start_time'))}\n"
                f"Duration: {self._format_duration(fields.get('duration_minutes'))}\n"
                f"Location: {fields.get('location') or 'Not specified'}\n\n"
                "Should I save it?"
            )
        label = "Reminder" if kind == "reminder" else "Task"
        return (
            "I’ve got this:\n\n"
            f"{label}: {fields.get('title', label)}\n"
            f"When: {fields.get('due_at') or fields.get('date') or 'Not specified'}\n\n"
            "Should I save it?"
        )

    def _question_for(self, kind: str, field: str) -> str:
        if kind == "meeting":
            return {
                "title": "Who is the meeting with?",
                "date": "Sure. What day should I set it for?",
                "start_time": "Sure. What time should I set it for?",
                "duration": "How long should it last?",
            }.get(field, "What detail should I add?")
        return {
            "title": "What should I call it?",
            "date": "When should I remind you?",
        }.get(field, "When should I set it for?")

    def _date_hint(self, text: str) -> date | None:
        lower = text.lower()
        today = datetime.now(UTC).date()
        if "tomorrow" in lower:
            return today + timedelta(days=1)
        if "today" in lower:
            return today
        weekdays = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        for name, index in weekdays.items():
            if name in lower:
                days = (index - today.weekday()) % 7 or 7
                return today + timedelta(days=days)
        return None

    def _time_hint(self, text: str) -> tuple[int, int] | None:
        if match := re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE):
            hour = int(match.group(1))
            minute = int(match.group(2) or 0)
            ampm = match.group(3).lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            return hour, minute
        return None

    def _duration_minutes(self, text: str) -> int | None:
        lower = text.lower()
        if match := re.search(r"\b(\d+)\s*(minutes?|mins?)\b", lower):
            return int(match.group(1))
        if match := re.search(r"\b(\d+)\s*(hours?|hrs?)\b", lower):
            return int(match.group(1)) * 60
        if "one hour" in lower or "an hour" in lower:
            return 60
        if "half hour" in lower or "30 minutes" in lower:
            return 30
        return None

    def _location_hint(self, text: str) -> str | None:
        if match := re.search(r"\b(?:at|in)\s+([A-Z][\w\s\d-]{2,40})$", text.strip()):
            return match.group(1).strip()
        return None

    def _person_after_with(self, text: str) -> str | None:
        if match := re.search(r"\bwith\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", text):
            return match.group(1)
        return None

    def _person_after_meet(self, text: str) -> str | None:
        if match := re.search(r"\bmeet(?:ing)?\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", text):
            return match.group(1)
        return None

    def _task_title(self, text: str, *, item_type: str) -> str:
        cleaned = re.sub(r"^\s*remind\s+me\s+to\s+", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(today|tomorrow|on\s+\w+day|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = " ".join(cleaned.strip(" .").split())
        if not cleaned:
            return "Reminder" if item_type == "reminder" else "Task"
        return cleaned[:1].upper() + cleaned[1:255]

    def _clean_title(self, text: str, *, fallback: str) -> str:
        words = re.sub(r"\b(schedule|book|set up|have|tomorrow|today|at|am|pm)\b", "", text, flags=re.IGNORECASE)
        words = " ".join(words.strip(" .").split())
        return words[:80] or fallback

    def _created_label(self, created: list[dict[str, Any]]) -> str:
        if not created:
            return "it"
        first = created[0]
        if len(created) == 1:
            return f"{first.get('title', 'it')}"
        return f"{len(created)} items"

    def _parse_dt(self, value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    def _format_time(self, value: Any) -> str:
        parsed = self._parse_dt(str(value)) if value else None
        if parsed is None:
            return "Not specified"
        return parsed.strftime("%I:%M %p").lstrip("0")

    def _format_duration(self, value: Any) -> str:
        if not value:
            return "Not specified"
        minutes = int(value)
        if minutes % 60 == 0:
            hours = minutes // 60
            return f"{hours} hour" if hours == 1 else f"{hours} hours"
        return f"{minutes} minutes"


conversation_manager = ConversationManager()
