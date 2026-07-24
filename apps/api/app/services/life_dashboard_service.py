from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, Habit, HabitLog, KnowledgeEntity, Memory, TodayItem
from .next_item_helper_service import get_next_upcoming_item
from .companion_score_service import get_companion_score
from .emotional_continuity_service import get_emotional_continuity
from .goal_service import list_active_goals
from .life_area_service import get_life_area_insights
from .long_term_understanding_service import get_understanding_profile
from .proactive_conversation_service import list_proactive_prompts
from .today_item_service import list_today_items, today_item_to_dict


def _display_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    hour = value.hour % 12 or 12
    suffix = "AM" if value.hour < 12 else "PM"
    return f"{hour}:{value.minute:02d} {suffix}"


def _goal_progress(goal: Goal, items: list[TodayItem]) -> int:
    linked = [item for item in items if item.goal_id == goal.id]
    if not linked:
        return 0
    completed = len([item for item in linked if item.status == "completed"])
    return round((completed / len(linked)) * 100)


def _mood_label(memories: list[Memory]) -> str:
    sentiment_scores = [
        1 if row.sentiment == "positive" else -1 if row.sentiment == "negative" else 0
        for row in memories
        if row.sentiment
    ]
    if not sentiment_scores:
        return "Not enough signal yet"
    average = sum(sentiment_scores) / len(sentiment_scores)
    if average > 0.25:
        return "Improving"
    if average < -0.25:
        return "Needs care"
    return "Steady"


async def get_life_dashboard(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    now = datetime.now(UTC)
    start = now - timedelta(days=30)
    memories = list((await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.created_at >= start,
            Memory.user_approved.is_(True),
            Memory.paused.is_(False),
        ).order_by(Memory.created_at.desc()).limit(100)
    )).scalars().all())
    goals = await list_active_goals(db, user_id, limit=10)
    areas = await get_life_area_insights(db, user_id)
    score = await get_companion_score(db, user_id)
    continuity = await get_emotional_continuity(db, user_id)
    understanding = await get_understanding_profile(db, user_id)
    prompts = await list_proactive_prompts(db, user_id, status="pending")

    people = Counter()
    learning = Counter()
    wins = []
    lessons = []
    breakthroughs = []
    mood_by_day: dict[str, list[int]] = defaultdict(list)
    for memory in memories:
        text = f"{memory.title} {memory.content}".lower()
        for token in ("wife", "friend", "mentor", "family", "customer", "client", "partner"):
            if token in text:
                people[token] += 1
        for token in ("study", "learn", "course", "book", "training", "reading"):
            if token in text:
                learning[token] += 1
        if memory.type in {"win", "milestone"}:
            wins.append(memory.title)
        if memory.type in {"decision", "emotional_pattern"}:
            lessons.append(memory.title)
        if memory.type in {"important_event", "project"}:
            breakthroughs.append(memory.title)
        if memory.sentiment:
            mood_by_day[memory.created_at.date().isoformat()].append(1 if memory.sentiment == "positive" else -1 if memory.sentiment == "negative" else 0)

    mood_trend = {
        "days": [
            {"date": day, "average": round(sum(vals) / len(vals), 2), "count": len(vals)}
            for day, vals in sorted(mood_by_day.items())
        ]
    }
    return {
        "goals_progress": [
            {"title": goal.title, "life_area": goal.life_area, "status": goal.status}
            for goal in goals
        ],
        "mood_trend": mood_trend,
        "people_mentioned": [{"name": name, "count": count} for name, count in people.most_common(6)],
        "learning_topics": [{"topic": topic, "count": count} for topic, count in learning.most_common(6)],
        "growth_wins": wins[:6],
        "lessons": lessons[:6],
        "breakthroughs": breakthroughs[:6],
        "emotional_continuity": continuity,
        "companion_score": score,
        "proactive_prompts": [
            {
                "id": row.id,
                "trigger_type": row.trigger_type,
                "prompt": row.prompt,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "status": row.status,
                "priority": row.priority,
                "scheduled_for": row.scheduled_for,
                "delivered_at": row.delivered_at,
                "dismissed_at": row.dismissed_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in prompts[:5]
        ],
        "life_area_balance": areas,
        "understanding": understanding,
    }


async def get_living_dashboard(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    today = date.today()
    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)

    today_items = await list_today_items(db, user_id, today)
    next_item = await get_next_upcoming_item(db, user_id, now)
    goals = list((await db.execute(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status.in_(["active", "in_progress"]))
        .order_by(Goal.priority.desc(), Goal.created_at.desc())
        .limit(8)
    )).scalars().all())
    habits = list((await db.execute(
        select(Habit)
        .where(Habit.user_id == user_id, Habit.status == "active")
        .order_by(Habit.created_at.desc())
        .limit(8)
    )).scalars().all())
    habit_logs = list((await db.execute(
        select(HabitLog)
        .where(HabitLog.user_id == user_id, HabitLog.logged_at >= thirty_days_ago)
    )).scalars().all())
    memories = list((await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.created_at >= thirty_days_ago,
            Memory.user_approved.is_(True),
            Memory.paused.is_(False),
            Memory.approval_status == "approved",
        )
        .order_by(Memory.created_at.desc())
        .limit(60)
    )).scalars().all())
    people = list((await db.execute(
        select(KnowledgeEntity)
        .where(KnowledgeEntity.user_id == user_id, KnowledgeEntity.entity_type.in_(["person", "relationship"]))
        .order_by(KnowledgeEntity.updated_at.desc())
        .limit(6)
    )).scalars().all())

    open_items = [item for item in today_items if item.status not in {"completed", "cancelled", "dismissed"}]
    completed_items = [item for item in today_items if item.status == "completed"]
    if next_item is None and open_items:
        next_item = sorted(
            open_items,
            key=lambda item: item.start_time or item.due_at or item.created_at,
        )[0]
    completion = round((len(completed_items) / len(today_items)) * 100) if today_items else 0

    focus_minutes = 0
    for item in today_items:
        if item.type != "focus":
            continue
        metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
        duration = metadata.get("duration_minutes") or metadata.get("actual_minutes") or metadata.get("planned_minutes")
        if isinstance(duration, int | float):
            focus_minutes += int(duration)

    habit_log_counts = Counter(str(row.habit_id) for row in habit_logs)
    goal_cards = [
        {
            "id": str(goal.id),
            "title": goal.title,
            "life_area": goal.life_area,
            "status": goal.status,
            "progress": _goal_progress(goal, today_items),
        }
        for goal in goals
    ]
    habit_cards = [
        {
            "id": str(habit.id),
            "name": habit.name,
            "life_area": habit.life_area,
            "frequency": habit.frequency,
            "recent_logs": habit_log_counts.get(str(habit.id), 0),
        }
        for habit in habits
    ]
    relationship_cards = [
        {
            "id": str(person.id),
            "name": person.name,
            "type": person.entity_type,
            "description": person.description,
        }
        for person in people
    ]

    insights: list[str] = []
    if next_item:
        insights.append(f"Your next item is {next_item.title}{f' at {_display_time(next_item.start_time or next_item.due_at)}' if _display_time(next_item.start_time or next_item.due_at) else ''}.")
    if completion:
        insights.append(f"You have completed {completion}% of today's agenda.")
    if memories:
        latest_signal = memories[0].title
        insights.append(f"Recent context points toward: {latest_signal}.")

    return {
        "status": "ok",
        "greeting": "Good evening" if now.hour >= 17 else "Good afternoon" if now.hour >= 12 else "Good morning",
        "today": {
            "date": today.isoformat(),
            "total": len(today_items),
            "open": len(open_items),
            "completed": len(completed_items),
            "completion_percent": completion,
        },
        "next_up": today_item_to_dict(next_item) if next_item else None,
        "mood": {"trend": _mood_label(memories), "signals": len([row for row in memories if row.sentiment])},
        "goals": goal_cards,
        "focus": {"minutes_today": focus_minutes, "hours_today": round(focus_minutes / 60, 2)},
        "relationships": relationship_cards,
        "habits": habit_cards,
        "insights": insights,
    }
