from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessProject, CalendarEventCache, Meeting, ProjectRoom, Reminder, Task, User
from ..services.business_context_service import list_projects, match_project_for_text
from ..services.memory_service import search_memories, summarize_recent_conversations
from ..services.plan_extractor import extract_plan
from ..services.profile_service import get_or_create_profile, profile_snapshot
from ..services.proactive_conversation_service import get_or_create_preferences
from ..services.project_room_service import list_rooms
from ..services.reminder_service import list_reminders
from ..services.today_item_service import list_today_items
from ..services import tasks as task_svc
from . import plan_draft as draft_svc


_DONE_STATUSES = {"done", "completed", "cancelled", "dismissed", "skipped"}


@dataclass(slots=True)
class PlanningContext:
    user_id: UUID
    current_datetime: datetime
    timezone: str
    planning_date: date
    user_message: str
    source_context: dict[str, Any]
    calendar_items: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    memory: list[dict[str, Any]]
    recent_conversation_summary: str
    unfinished_items: list[dict[str, Any]]
    preferences: dict[str, Any]
    explicit_constraints: dict[str, Any]
    request_items: list[dict[str, Any]]
    request_focus: list[str]
    request_summary: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "current_datetime": self.current_datetime.isoformat(),
            "timezone": self.timezone,
            "planning_date": self.planning_date.isoformat(),
            "user_message": self.user_message,
            "source_context": self.source_context,
            "calendar_items": self.calendar_items,
            "tasks": self.tasks,
            "reminders": self.reminders,
            "projects": self.projects,
            "memory": self.memory,
            "recent_conversation_summary": self.recent_conversation_summary,
            "unfinished_items": self.unfinished_items,
            "preferences": self.preferences,
            "explicit_constraints": self.explicit_constraints,
            "request_items": self.request_items,
            "request_focus": self.request_focus,
            "request_summary": self.request_summary,
        }


def _to_dict_task(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "priority": int(task.priority or 1),
        "status": task.status,
        "source": task.source,
        "goal_id": str(task.goal_id) if task.goal_id else None,
        "estimated_minutes": int(task.estimated_minutes or 30),
        "category": task.category,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _to_dict_meeting(meeting: Meeting) -> dict[str, Any]:
    return {
        "id": str(meeting.id),
        "title": meeting.title,
        "start_time": meeting.start_time.isoformat() if meeting.start_time else None,
        "end_time": meeting.end_time.isoformat() if meeting.end_time else None,
        "participants": meeting.participants or [],
        "location": meeting.location,
        "meeting_link": meeting.meeting_link,
        "project_id": str(meeting.project_id) if meeting.project_id else None,
        "notes": meeting.notes,
        "status": meeting.status,
    }


def _to_dict_reminder(reminder: Reminder) -> dict[str, Any]:
    return {
        "id": str(reminder.id),
        "title": reminder.title,
        "remind_at": reminder.remind_at.isoformat() if reminder.remind_at else None,
        "status": reminder.status,
        "task_id": reminder.task_id,
        "recurrence_rule": reminder.recurrence_rule,
    }


def _to_dict_project(project: BusinessProject) -> dict[str, Any]:
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "goals": project.goals or [],
        "key_people": project.key_people or [],
        "risks": project.risks or [],
        "opportunities": project.opportunities or [],
    }


def _to_dict_room(room: ProjectRoom) -> dict[str, Any]:
    return {
        "id": str(room.id),
        "name": room.name,
        "description": room.description,
        "status": room.status,
        "business_project_id": str(room.business_project_id) if room.business_project_id else None,
    }


def _to_dict_memory(memory) -> dict[str, Any]:
    return {
        "id": str(memory.id),
        "title": memory.title,
        "type": memory.type,
        "life_area": memory.life_area,
        "content": memory.content[:300],
        "importance": int(memory.importance or 0),
        "sentiment": memory.sentiment,
        "created_at": memory.created_at.isoformat() if memory.created_at else None,
    }


def _day_bounds_local(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start, start + timedelta(days=1)


def _is_open_status(status: str | None) -> bool:
    return (status or "").lower() not in _DONE_STATUSES


def _meeting_day_filter(day_start: datetime, day_end: datetime):
    return or_(
        and_(Meeting.start_time.is_not(None), Meeting.start_time >= day_start, Meeting.start_time < day_end),
        and_(Meeting.start_time.is_(None), Meeting.created_at >= day_start, Meeting.created_at < day_end),
    )


def _calendar_day_filter(day_start: datetime, day_end: datetime):
    return or_(
        and_(CalendarEventCache.starts_at >= day_start, CalendarEventCache.starts_at < day_end),
        and_(CalendarEventCache.ends_at.is_not(None), CalendarEventCache.ends_at >= day_start, CalendarEventCache.ends_at < day_end),
    )


def _extract_request_focus(message: str) -> list[str]:
    lower = (message or "").lower()
    focus: list[str] = []
    mapping = (
        ("school", "school"),
        ("coding", "coding"),
        ("code", "coding"),
        ("work", "work"),
        ("business", "business"),
        ("family", "family"),
        ("health", "health"),
        ("fitness", "health"),
        ("church", "church"),
        ("spiritual", "spiritual"),
    )
    for needle, label in mapping:
        if needle in lower and label not in focus:
            focus.append(label)
    return focus


def _is_generic_request_title(title: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (title or "")).strip().lower()
    if not cleaned:
        return True
    if cleaned in {
        "day",
        "plan",
        "plan my day",
        "today",
        "task",
        "tasks",
        "meeting",
        "work",
        "project",
        "thing",
        "things",
    }:
        return True
    if cleaned.startswith("work on "):
        return True
    if cleaned.startswith("meeting ") and len(cleaned.split()) <= 2:
        return True
    return False


def _parse_planning_constraints(message: str, source_context: dict[str, Any] | None, tz: ZoneInfo, now: datetime) -> dict[str, Any]:
    text = f"{message or ''} {source_context or {}}".lower()
    constraints: dict[str, Any] = {
        "time_limit_minutes": None,
        "energy": "normal",
        "hard_cutoff": None,
        "must_finish": [],
        "must_have": [],
    }

    import re

    if match := re.search(r"\b(\d{1,2})\s*hours?\b", text):
        constraints["time_limit_minutes"] = max(30, int(match.group(1)) * 60)
    elif match := re.search(r"\bonly have\s+(\d{1,2})\s*hours?\b", text):
        constraints["time_limit_minutes"] = max(30, int(match.group(1)) * 60)

    if "tired" in text or "exhausted" in text or "burned out" in text or "burnt out" in text:
        constraints["energy"] = "low"

    cutoff = None
    if match := re.search(r"\bdon't schedule anything after\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        ampm = (match.group(3) or "").lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        cutoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif match := re.search(r"\bby\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        ampm = match.group(3).lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        cutoff = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif "after 8pm" in text:
        cutoff = now.replace(hour=20, minute=0, second=0, microsecond=0)

    if cutoff is not None:
        constraints["hard_cutoff"] = cutoff.isoformat()

    if "focus on work first" in text or "work first" in text:
        constraints["must_have"].append("work")
    if "church" in text:
        constraints["must_have"].append("church")
    if "school" in text:
        constraints["must_have"].append("school")
    if "coding" in text or "code" in text:
        constraints["must_have"].append("coding")

    return constraints


def _project_mentions(message: str, projects: list[dict[str, Any]], rooms: list[dict[str, Any]]) -> list[str]:
    text = (message or "").lower()
    mentions: list[str] = []
    for item in [*projects, *rooms]:
        name = str(item.get("name") or "").strip()
        if name and name.lower() in text and name not in mentions:
            mentions.append(name)
    return mentions


def _score_candidate(
    candidate: dict[str, Any],
    context: PlanningContext,
    focus_projects: list[str],
) -> int:
    score = int(candidate.get("priority") or 1) * 10
    due_at = candidate.get("due_at")
    if due_at:
        score += 20
        if str(due_at)[:10] == context.planning_date.isoformat():
            score += 8
    if candidate.get("status") in {"in_progress", "planned"}:
        score += 6
    title = f"{candidate.get('title') or ''} {candidate.get('notes') or ''}".lower()
    for project in focus_projects:
        if project.lower() in title:
            score += 15
    for focus in context.request_focus:
        if focus in title:
            score += 10
    if any(term in title for term in ("urgent", "important", "deadline", "due")):
        score += 8
    if candidate.get("source") in {"yesterday", "overdue", "request"}:
        score += 12
    return score


def _task_to_candidate(task: Task, *, source: str, weight: int = 1) -> dict[str, Any]:
    return _to_dict_task(task) | {"source": source, "priority": max(int(task.priority or 1), weight)}


def _light_schedule(
    context: PlanningContext,
    proposed_tasks: list[dict[str, Any]],
    fixed_items: list[dict[str, Any]],
    focus_projects: list[str],
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    follow_up = None
    if not proposed_tasks and not fixed_items:
        follow_up = "What absolutely has to happen today, and how much time do you really have?"
    schedule: list[dict[str, Any]] = []
    total_minutes = 0
    hard_stop = context.current_datetime.replace(hour=20, minute=0, second=0, microsecond=0)
    if context.explicit_constraints.get("hard_cutoff"):
        hard_stop = datetime.fromisoformat(str(context.explicit_constraints["hard_cutoff"]))
    cursor = context.current_datetime
    if cursor.hour < 9:
        cursor = cursor.replace(hour=9, minute=0, second=0, microsecond=0)
    if cursor > hard_stop:
        cursor = hard_stop - timedelta(minutes=90)
    breaks_every = 45 if context.explicit_constraints.get("energy") == "low" else 90
    max_items = 3 if context.explicit_constraints.get("energy") == "low" else 5
    if context.explicit_constraints.get("time_limit_minutes"):
        max_items = min(max_items, max(2, int(context.explicit_constraints["time_limit_minutes"]) // 45))
    for fixed in fixed_items:
        start = fixed.get("start_time")
        if not start:
            continue
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(fixed["end_time"]) if fixed.get("end_time") else start_dt + timedelta(minutes=60)
        schedule.append(
            {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat(),
                "title": fixed["title"],
                "kind": fixed.get("type", "confirmed"),
                "confirmed": True,
                "reason": "Fixed calendar item.",
            }
        )
        cursor = max(cursor, end_dt)

    for item in proposed_tasks[:max_items]:
        minutes = int(item.get("estimated_minutes") or 30)
        if context.explicit_constraints.get("energy") == "low":
            minutes = min(minutes, 30)
        if context.explicit_constraints.get("time_limit_minutes"):
            remaining = int(context.explicit_constraints["time_limit_minutes"]) - total_minutes
            if remaining <= 0:
                break
            minutes = min(minutes, remaining)
        end = cursor + timedelta(minutes=minutes)
        if end > hard_stop:
            break
        schedule.append(
            {
                "start": cursor.isoformat(),
                "end": end.isoformat(),
                "title": item["title"],
                "kind": "task",
                "confirmed": False,
                "reason": item.get("notes") or "Suggested from current context.",
            }
        )
        total_minutes += minutes
        cursor = end
        if total_minutes and total_minutes % breaks_every == 0 and cursor + timedelta(minutes=15) < hard_stop:
            cursor = cursor + timedelta(minutes=15)
            schedule.append(
                {
                    "start": (cursor - timedelta(minutes=15)).isoformat(),
                    "end": cursor.isoformat(),
                    "title": "Break",
                    "kind": "break",
                    "confirmed": True,
                    "reason": "Protect a realistic pause.",
                }
            )

    risks: list[str] = []
    if fixed_items and any("church" in str(item.get("title", "")).lower() for item in fixed_items):
        risks.append("Church is fixed, so the day needs a clean buffer before it.")
    if context.explicit_constraints.get("energy") == "low":
        risks.append("Energy looks low, so overpacking the day would backfire.")
    if context.explicit_constraints.get("time_limit_minutes") and total_minutes >= int(context.explicit_constraints["time_limit_minutes"]):
        risks.append("The time limit is tight, so a longer backlog will need another day.")
    if not risks:
        risks.append("No hard conflicts detected.")
    return schedule, risks, follow_up


def _natural_response(context: PlanningContext, priorities: list[dict[str, Any]], schedule: list[dict[str, Any]], follow_up_question: str | None) -> str:
    hooks: list[str] = []
    if priorities:
        top_titles = [str(item["title"]) for item in priorities[:3]]
        if top_titles:
            hooks.append("I built today around " + ", ".join(top_titles[:2]) + (" and " + top_titles[2] if len(top_titles) > 2 else "") + ".")
    if context.request_focus:
        hooks.append(f"I also kept your focus on {', '.join(context.request_focus)}.")
    if context.explicit_constraints.get("energy") == "low":
        hooks.append("I kept this lighter because you said you're tired.")
    if context.explicit_constraints.get("time_limit_minutes"):
        hours = max(1, int(context.explicit_constraints["time_limit_minutes"]) // 60)
        hooks.append(f"I stayed within about {hours} hour{'s' if hours != 1 else ''}.")
    if any("church" in str(item.get("title", "")).lower() for item in schedule):
        hooks.append("I left room for church and the surrounding buffer.")
    if not hooks:
        hooks.append("I based this on your open work, calendar, reminders, and recent context.")
    if follow_up_question:
        hooks.append(follow_up_question)
    return " ".join(hooks)


async def build_planning_context(
    db: AsyncSession,
    user: User,
    *,
    user_message: str = "",
    source_context: dict[str, Any] | None = None,
    target_date: date | None = None,
) -> PlanningContext:
    tz_name = user.timezone or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    current_datetime = datetime.now(tz)
    planning_date = target_date or current_datetime.date()
    yesterday = planning_date - timedelta(days=1)
    day_start, day_end = _day_bounds_local(planning_date, tz)
    yesterday_start, yesterday_end = _day_bounds_local(yesterday, tz)

    task_rows = await task_svc.list_tasks(db, user.id, top_level_only=True)
    tasks = [_to_dict_task(task) for task in task_rows]
    open_tasks = [task for task in task_rows if _is_open_status(task.status)]
    overdue_tasks = [task for task in open_tasks if task.due_at and task.due_at.astimezone(tz) < current_datetime]
    yesterday_tasks = await task_svc.list_tasks(db, user.id, day=yesterday, top_level_only=True)

    reminder_rows = await list_reminders(db, user.id)
    reminders = [_to_dict_reminder(reminder) for reminder in reminder_rows if reminder.remind_at.astimezone(tz).date() >= yesterday]

    meeting_stmt = select(Meeting).where(Meeting.user_id == user.id, _meeting_day_filter(day_start, day_end))
    meeting_result = await db.execute(meeting_stmt.order_by(Meeting.start_time.asc().nulls_last()))
    meetings = list(meeting_result.scalars().all())

    calendar_stmt = select(CalendarEventCache).where(CalendarEventCache.user_id == user.id, _calendar_day_filter(day_start, day_end))
    calendar_result = await db.execute(calendar_stmt.order_by(CalendarEventCache.starts_at.asc()))
    calendar_cache = list(calendar_result.scalars().all())

    today_item_rows = await list_today_items(db, user.id, planning_date)
    yesterday_items = await list_today_items(db, user.id, yesterday)

    projects = [_to_dict_project(project) for project in await list_projects(db, user.id)]
    rooms = [_to_dict_room(room) for room in await list_rooms(db, user.id)]
    focus_projects = _project_mentions(user_message, projects, rooms)
    matched_project = await match_project_for_text(db, user.id, user_message) if user_message.strip() else None
    if matched_project is not None:
        focus_projects.insert(0, matched_project.name)
    focus_projects = list(dict.fromkeys(focus_projects))

    profile = await get_or_create_profile(db, user)
    preferences = await get_or_create_preferences(db, user.id)
    recent_conversation_summary = await summarize_recent_conversations(db, user.id, limit=8)
    request_plan = await extract_plan(
        user_message or "Plan my day",
        wake_name=user.wake_name or user.display_name or "friend",
        timezone=tz_name,
        history_summary=recent_conversation_summary,
        today=planning_date,
    )
    memory_rows = await search_memories(db, user.id, user_message or recent_conversation_summary or "today", limit=6)
    request_focus = _extract_request_focus(user_message)
    explicit_constraints = _parse_planning_constraints(user_message, source_context, tz, current_datetime)

    calendar_items = [
        _to_dict_meeting(meeting) | {"kind": "meeting", "confirmed": True}
        for meeting in meetings
    ]
    calendar_items.extend(
        {
            "id": str(item.id),
            "title": item.title,
            "start_time": item.starts_at.isoformat() if item.starts_at else None,
            "end_time": item.ends_at.isoformat() if item.ends_at else None,
            "kind": "calendar_cache",
            "confirmed": True,
        }
        for item in calendar_cache
    )
    calendar_items.extend(
        {
            "id": str(item.id),
            "title": item.title,
            "start_time": item.start_time.isoformat() if item.start_time else None,
            "end_time": item.end_time.isoformat() if item.end_time else None,
            "kind": item.type,
            "confirmed": _is_open_status(item.status) is False,
        }
        for item in today_item_rows
        if item.type in {"meeting", "calendar"}
    )

    unfinished_items = [
        _to_dict_task(task, source="overdue")
        for task in overdue_tasks
    ]
    unfinished_items.extend(
        _to_dict_task(task, source="yesterday")
        for task in yesterday_tasks
        if _is_open_status(task.status)
    )
    unfinished_items.extend(
        {
            "id": str(item.id),
            "title": item.title,
            "kind": item.type,
            "status": item.status,
            "due_at": item.due_at.isoformat() if item.due_at else None,
            "start_time": item.start_time.isoformat() if item.start_time else None,
        }
        for item in yesterday_items
        if _is_open_status(item.status)
    )

    request_items = list(request_plan.get("proposed_tasks") or [])
    request_items = [
        item
        for item in request_items
        if isinstance(item, dict)
        and item.get("title")
        and not _is_generic_request_title(str(item["title"]))
    ]

    return PlanningContext(
        user_id=user.id,
        current_datetime=current_datetime,
        timezone=tz_name,
        planning_date=planning_date,
        user_message=user_message,
        source_context=source_context or {},
        calendar_items=calendar_items,
        tasks=tasks,
        reminders=reminders,
        projects=projects + rooms,
        memory=[_to_dict_memory(memory) for memory in memory_rows],
        recent_conversation_summary=recent_conversation_summary,
        unfinished_items=unfinished_items,
        preferences=profile_snapshot(user, profile) | {
            "companion": {
                "tone": preferences.tone,
                "response_length": preferences.response_length,
                "directness_level": preferences.directness_level,
                "voice_pace": preferences.voice_pace,
                "humor_level": preferences.humor_level,
            }
        },
        explicit_constraints=explicit_constraints,
        request_items=request_items,
        request_focus=request_focus,
        request_summary=str(request_plan.get("clarifying_question") or ""),
    )


def _to_dict_task(task: Task, *, source: str | None = None) -> dict[str, Any]:
    payload = _to_dict_task_base(task)
    if source:
        payload["source"] = source
    return payload


def _to_dict_task_base(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "notes": task.notes,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "priority": int(task.priority or 1),
        "status": task.status,
        "estimated_minutes": int(task.estimated_minutes or 30),
        "category": task.category,
    }


def _plan_from_context(context: PlanningContext) -> dict[str, Any]:
    fixed_items = sorted(
        [item for item in context.calendar_items if item.get("start_time")],
        key=lambda item: item["start_time"],
    )
    request_candidates = []
    known_titles = {
        str(item.get("title") or "").strip().lower()
        for item in context.tasks + context.reminders + context.unfinished_items + context.calendar_items
        if item.get("title")
    }
    for item in context.request_items:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        title = str(item["title"]).strip()
        title_lower = title.lower()
        if _is_generic_request_title(title):
            continue
        if any(title_lower == known or title_lower in known or known in title_lower for known in known_titles if known):
            continue
        request_candidates.append(
            {
                "title": title,
                "notes": item.get("notes"),
                "due_at": item.get("due_at"),
                "estimated_minutes": int(item.get("estimated_minutes") or 30),
                "priority": int(item.get("priority") or 1),
                "category": item.get("category") or "task",
                "source": item.get("source") or "request",
            }
        )

    task_candidates = []
    for task in context.tasks:
        if not _is_open_status(task.get("status")):
            continue
        task_candidates.append(
            {
                "title": task["title"],
                "notes": task.get("notes"),
                "due_at": task.get("due_at"),
                "estimated_minutes": int(task.get("estimated_minutes") or 30),
                "priority": int(task.get("priority") or 1),
                "category": task.get("category") or "task",
                "source": "task",
                "status": task.get("status"),
            }
        )

    rem_candidates = [
        {
            "title": rem["title"],
            "notes": rem.get("recurrence_rule"),
            "due_at": rem.get("remind_at"),
            "estimated_minutes": 15,
            "priority": 2 if rem.get("status") == "scheduled" else 1,
            "category": "reminder",
            "source": "reminder",
            "status": rem.get("status"),
        }
        for rem in context.reminders
        if rem.get("remind_at")
    ]

    unfinished_candidates = []
    for item in context.unfinished_items:
        if not item.get("title"):
            continue
        if item.get("kind") == "reminder":
            continue
        unfinished_candidates.append(
            {
                "title": item["title"],
                "notes": item.get("notes"),
                "due_at": item.get("due_at"),
                "estimated_minutes": int(item.get("estimated_minutes") or 30),
                "priority": int(item.get("priority") or 1),
                "category": item.get("category") or "task",
                "source": item.get("source") or "unfinished",
            }
        )

    focus_projects = [str(project.get("name") or "") for project in context.projects if project.get("name")]
    merged = request_candidates + task_candidates + rem_candidates + unfinished_candidates
    scored = sorted(
        merged,
        key=lambda item: (
            -_score_candidate(item, context, focus_projects),
            item.get("due_at") or "",
            -(int(item.get("priority") or 1)),
        ),
    )
    seen: set[tuple[str, str | None]] = set()
    prioritized: list[dict[str, Any]] = []
    for item in scored:
        key = (str(item["title"]).lower(), str(item.get("due_at") or ""))
        if key in seen:
            continue
        seen.add(key)
        prioritized.append(item)

    if context.explicit_constraints.get("energy") == "low":
        prioritized = prioritized[:4]
    elif context.explicit_constraints.get("time_limit_minutes"):
        prioritized = prioritized[: max(3, int(context.explicit_constraints["time_limit_minutes"]) // 60 + 1)]
    else:
        prioritized = prioritized[:6]

    if not prioritized:
        busy_hours = {
            datetime.fromisoformat(str(item["start_time"]).replace("Z", "+00:00")).hour
            for item in fixed_items
            if item.get("start_time")
        }
        review_hour = next((hour for hour in (9, 11, 14, 16) if hour not in busy_hours), 17)
        review_at = datetime.combine(
            context.planning_date,
            time(hour=review_hour),
            tzinfo=ZoneInfo(context.timezone),
        )
        prioritized = [
            {
                "title": "Daily review and reset",
                "notes": "Keep the plan light around fixed calendar commitments.",
                "due_at": review_at.isoformat(),
                "estimated_minutes": 20,
                "priority": 1,
                "category": "reflection",
                "source": "planner_fallback",
            }
        ]

    calendar_blocks = []
    for item in fixed_items:
        calendar_blocks.append(
            {
                "start": item.get("start_time"),
                "end": item.get("end_time"),
                "title": item.get("title"),
                "kind": item.get("kind"),
                "confirmed": True,
                "reason": "Fixed calendar item.",
            }
        )

    schedule, risks, follow_up_question = _light_schedule(context, prioritized, calendar_blocks, focus_projects)
    if not calendar_blocks and prioritized[0].get("source") == "planner_fallback":
        schedule = [
            {
                "start": context.current_datetime.isoformat(),
                "end": (context.current_datetime + timedelta(minutes=30)).isoformat(),
                "title": "Morning review",
                "kind": "light_block",
                "confirmed": False,
                "reason": "No strong context yet, so keep the plan light.",
            },
            {
                "start": (context.current_datetime + timedelta(minutes=45)).isoformat(),
                "end": (context.current_datetime + timedelta(minutes=105)).isoformat(),
                "title": "One focused block",
                "kind": "light_block",
                "confirmed": False,
                "reason": "Use the time you actually have.",
            },
        ]

    personalized_summary = _natural_response(context, prioritized, schedule, follow_up_question)
    priorities = [
        {
            "title": item["title"],
            "reason": item.get("notes") or "High priority based on current context.",
            "source": item.get("source"),
            "confirmed": item.get("source") != "request",
        }
        for item in prioritized[:4]
    ]
    proposed_tasks = [
        {
            "title": item["title"],
            "notes": item.get("notes") or "Plan draft. Confirm before adding to Today.",
            "due_at": item.get("due_at"),
            "estimated_minutes": item.get("estimated_minutes") or 30,
            "priority": item.get("priority") or 1,
            "category": item.get("category") or "task",
            "type": "task",
        }
        for item in prioritized
        if item.get("source") != "reminder"
    ]

    result = {
        "intent": "daily_plan",
        "proposed_tasks": proposed_tasks,
        "clarifying_question": follow_up_question,
        "personalized_summary": personalized_summary,
        "priorities": priorities,
        "suggested_schedule": schedule,
        "risks_or_conflicts": risks,
        "follow_up_question": follow_up_question,
        "natural_response": personalized_summary,
        "planning_context": context.as_dict(),
    }
    return result


def _dt(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=minute))


def _draft_item(day: date, hour: int, title: str, *, category: str = "work", minutes: int = 45, priority: int = 1) -> dict[str, Any]:
    return {
        "title": title,
        "due_at": _dt(day, hour).isoformat(),
        "estimated_minutes": minutes,
        "priority": priority,
        "category": category,
        "notes": "Planner draft. Confirm before adding to Today.",
    }


async def _existing_constraints(db: AsyncSession, user_id, day: date) -> list[dict[str, Any]]:
    return [
        {
            "title": item.title,
            "type": item.type,
            "start_time": item.start_time.isoformat() if item.start_time else None,
            "due_at": item.due_at.isoformat() if item.due_at else None,
        }
        for item in await list_today_items(db, user_id, day)
        if item.status not in {"completed", "cancelled", "dismissed"}
    ]


async def balance_plan(db: AsyncSession, user_id, plan: list[dict[str, Any]], constraints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    busy_hours = set()
    for item in constraints:
        raw = item.get("start_time") or item.get("due_at")
        if raw:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            busy_hours.add(parsed.hour)
    balanced = []
    for item in plan:
        due_at = datetime.fromisoformat(str(item["due_at"]).replace("Z", "+00:00"))
        while due_at.hour in busy_hours and due_at.hour < 17:
            due_at += timedelta(hours=1)
        busy_hours.add(due_at.hour)
        item = dict(item)
        item["due_at"] = due_at.isoformat()
        balanced.append(item)
    return balanced


async def _save_plan(db: AsyncSession, user: User, intent: str, proposed_tasks: list[dict[str, Any]], *, clarifying_question: str | None = None) -> dict[str, Any]:
    payload = {
        "intent": intent,
        "proposed_tasks": proposed_tasks,
        "clarifying_question": clarifying_question,
        "requires_confirmation": True,
    }
    await draft_svc.save_draft(db, user.id, payload)
    return payload


async def generate_daily_plan(
    db: AsyncSession,
    user: User,
    target_date: date | None = None,
    *,
    planning_context: PlanningContext | None = None,
    user_message: str = "",
    source_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = planning_context
    if context is None:
        context = await build_planning_context(
            db,
            user,
            user_message=user_message,
            source_context=source_context,
            target_date=target_date,
        )

    plan_payload = _plan_from_context(context)
    plan_payload["requires_confirmation"] = bool(plan_payload.get("proposed_tasks"))
    await draft_svc.save_draft(db, user.id, plan_payload)
    return plan_payload


async def generate_weekly_plan(db: AsyncSession, user: User, week_start: date | None = None) -> dict[str, Any]:
    start = week_start or (date.today() - timedelta(days=date.today().weekday()))
    tasks: list[dict[str, Any]] = []
    themes = [
        "Set weekly priorities",
        "Deep work on main project",
        "Relationship and follow-up block",
        "Review commitments",
        "Weekly reflection",
    ]
    for offset, title in enumerate(themes):
        day = start + timedelta(days=offset)
        constraints = await _existing_constraints(db, user.id, day)
        item = _draft_item(day, 10 if offset < 4 else 15, title, category="weekly", minutes=50)
        tasks.extend(await balance_plan(db, user.id, [item], constraints))
    return await _save_plan(db, user, "weekly_plan", tasks)


async def generate_monthly_plan(db: AsyncSession, user: User, month: str | None = None) -> dict[str, Any]:
    today = date.today()
    start = date.fromisoformat(f"{month}-01") if month else today.replace(day=1)
    tasks = [
        _draft_item(start, 9, "Choose the month’s top outcome", category="monthly", minutes=45, priority=2),
        _draft_item(start + timedelta(days=7), 10, "Review project milestones", category="monthly", minutes=45),
        _draft_item(start + timedelta(days=14), 10, "Mid-month adjustment", category="monthly", minutes=35),
        _draft_item(start + timedelta(days=24), 15, "Monthly review and lessons", category="reflection", minutes=45),
    ]
    return await _save_plan(db, user, "monthly_plan", tasks)


async def generate_quarterly_plan(db: AsyncSession, user: User, quarter: str | None = None) -> dict[str, Any]:
    today = date.today()
    tasks = [
        _draft_item(today, 9, "Define quarterly outcomes", category="quarterly", minutes=60, priority=2),
        _draft_item(today + timedelta(days=30), 10, "Quarter checkpoint", category="quarterly", minutes=45),
        _draft_item(today + timedelta(days=60), 10, "Quarter execution review", category="quarterly", minutes=45),
    ]
    return await _save_plan(db, user, "quarterly_plan", tasks)


async def generate_90_day_plan(db: AsyncSession, user: User, goal_id: UUID | None = None) -> dict[str, Any]:
    today = date.today()
    tasks = [
        _draft_item(today, 9, "Clarify 90-day target", category="roadmap", minutes=50, priority=2),
        _draft_item(today + timedelta(days=30), 9, "30-day milestone review", category="roadmap", minutes=40),
        _draft_item(today + timedelta(days=60), 9, "60-day milestone review", category="roadmap", minutes=40),
        _draft_item(today + timedelta(days=88), 15, "90-day reflection and next roadmap", category="roadmap", minutes=50),
    ]
    if goal_id:
        for task in tasks:
            task["goal_id"] = str(goal_id)
    return await _save_plan(db, user, "90_day_plan", tasks)


async def generate_goal_roadmap(db: AsyncSession, user: User, goal_id: UUID) -> dict[str, Any]:
    return await generate_90_day_plan(db, user, goal_id=goal_id)


async def generate_life_roadmap(db: AsyncSession, user: User) -> dict[str, Any]:
    today = date.today()
    tasks = [
        _draft_item(today, 9, "Review life areas", category="life_roadmap", minutes=45),
        _draft_item(today + timedelta(days=7), 9, "Choose one area to improve", category="life_roadmap", minutes=45),
        _draft_item(today + timedelta(days=14), 9, "Create support rhythm", category="life_roadmap", minutes=45),
    ]
    return await _save_plan(db, user, "life_roadmap", tasks)


async def convert_plan_to_today_items(db: AsyncSession, user: User, draft_id: str = "current") -> list[dict[str, Any]]:
    return await draft_svc.confirm_draft(db, user.id, timezone=user.timezone or "UTC")
