import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from . import plan_draft as draft_svc
from . import plan_extractor
from . import tasks as task_svc

log = logging.getLogger("aipal.suggest_day")

ROUTINE_TEMPLATES = {
    "plan_day": "Suggest a balanced plan for the rest of my day with realistic time blocks.",
    "deep_work": "Block 90 minutes for deep focus work with a short warm-up.",
    "break": "Schedule short restorative breaks between my tasks today.",
    "errands": "Fit errands and quick wins into my afternoon.",
}

_TEMPLATE_TASKS = {
    "plan_day": [
        {"title": "Review priorities for the rest of today", "estimated_minutes": 15, "priority": 2, "category": "work"},
        {"title": "Focus block on your top task", "estimated_minutes": 45, "priority": 2, "category": "work"},
        {"title": "Short walk or stretch break", "estimated_minutes": 10, "priority": 0, "category": "health"},
        {"title": "Wrap up and plan tomorrow", "estimated_minutes": 15, "priority": 1, "category": "personal"},
    ],
    "deep_work": [
        {"title": "Warm up: clear inbox and set intention", "estimated_minutes": 10, "priority": 1, "category": "work"},
        {"title": "Deep focus block", "estimated_minutes": 90, "priority": 2, "category": "work"},
        {"title": "Decompress break", "estimated_minutes": 15, "priority": 0, "category": "health"},
    ],
    "break": [
        {"title": "Step away and stretch", "estimated_minutes": 10, "priority": 0, "category": "health"},
        {"title": "Hydrate and snack", "estimated_minutes": 10, "priority": 0, "category": "health"},
        {"title": "Short walk outside", "estimated_minutes": 15, "priority": 0, "category": "health"},
    ],
    "errands": [
        {"title": "Quick errand or pickup", "estimated_minutes": 30, "priority": 1, "category": "home"},
        {"title": "Inbox zero sweep", "estimated_minutes": 20, "priority": 1, "category": "work"},
        {"title": "One small home task", "estimated_minutes": 20, "priority": 0, "category": "home"},
    ],
}


def _template_fallback(
    template: str | None,
    open_tasks: list,
    today: date,
    tz: ZoneInfo,
) -> dict:
    """Build a draft when the LLM returns no tasks."""
    if template and template in _TEMPLATE_TASKS:
        tasks = [{**t, "due_at": None} for t in _TEMPLATE_TASKS[template]]
        return {"intent": "plan_day", "proposed_tasks": tasks, "clarifying_question": None}

    if open_tasks:
        tasks = []
        base_hour = max(datetime.now(tz).hour + 1, 9)
        for idx, t in enumerate(open_tasks[:4]):
            due_dt = datetime(today.year, today.month, today.day, min(base_hour + idx, 20), 0, tzinfo=tz)
            tasks.append(
                {
                    "title": f"Work on: {t.title}",
                    "due_at": due_dt.isoformat(),
                    "estimated_minutes": t.estimated_minutes or 30,
                    "priority": t.priority if t.priority is not None else 1,
                    "category": t.category or "personal",
                }
            )
        return {"intent": "plan_day", "proposed_tasks": tasks, "clarifying_question": None}

    now = datetime.now(tz)
    afternoon = datetime(today.year, today.month, today.day, max(now.hour + 1, 14), 0, tzinfo=tz)
    return {
        "intent": "plan_day",
        "proposed_tasks": [
            {
                "title": "Pick one thing that would make today feel good",
                "due_at": afternoon.isoformat(),
                "estimated_minutes": 30,
                "priority": 1,
                "category": "personal",
            },
            {
                "title": "Take a restorative break",
                "due_at": (afternoon + timedelta(hours=1)).isoformat(),
                "estimated_minutes": 15,
                "priority": 0,
                "category": "health",
            },
        ],
        "clarifying_question": None,
    }


async def suggest_day(
    db: AsyncSession,
    user: User,
    *,
    template: str | None = None,
) -> dict:
    today = date.today()
    try:
        tz = ZoneInfo(user.timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    tasks = await task_svc.list_tasks(db, user.id, day=today)
    open_tasks = [t for t in tasks if t.status in ("planned", "in_progress")]
    open_lines = []
    for t in open_tasks[:8]:
        line = t.title
        if t.due_at:
            line += f" (due {t.due_at.strftime('%H:%M')})"
        open_lines.append(line)
    open_summary = ", ".join(open_lines)

    if template and template in ROUTINE_TEMPLATES:
        message = ROUTINE_TEMPLATES[template]
    else:
        message = (
            "Suggest a thoughtful plan for the rest of my day based on my open tasks "
            "and what you know about me."
        )

    context_parts = []
    if user.about_me:
        context_parts.append(f"About me: {user.about_me[:500]}")
    if open_summary:
        context_parts.append(f"Open tasks today: {open_summary}")
    context_parts.append(message)
    user_message = "\n".join(context_parts)

    extracted = await plan_extractor.extract_plan(
        user_message,
        wake_name=user.wake_name or user.display_name or "friend",
        timezone=user.timezone or "UTC",
        today=today,
    )
    if not extracted.get("proposed_tasks"):
        log.info("suggest_day LLM empty for user %s template=%s — using fallback", user.id, template)
        extracted = _template_fallback(template, open_tasks, today, tz)
        regex = plan_extractor._regex_fallback(user_message, today, tz)
        if regex.get("proposed_tasks"):
            extracted = regex

    if extracted.get("proposed_tasks"):
        await draft_svc.save_draft(db, user.id, extracted)
    return extracted
