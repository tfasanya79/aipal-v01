from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, HabitLog, KnowledgeEntity, Meeting, Memory, Reflection, Task, TodayItem
from .life_area_service import get_life_area_insights


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _week_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or _utcnow()
    start_date = current.date() - timedelta(days=current.weekday())
    start = datetime.combine(start_date, datetime.min.time())
    return start, start + timedelta(days=7)


def _month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or _utcnow()
    start = datetime.combine(date(current.year, current.month, 1), datetime.min.time())
    if current.month == 12:
        end = datetime.combine(date(current.year + 1, 1, 1), datetime.min.time())
    else:
        end = datetime.combine(date(current.year, current.month + 1, 1), datetime.min.time())
    return start, end


def _period_clause(start: datetime, end: datetime):
    return and_(TodayItem.created_at >= start, TodayItem.created_at < end)


def _memory_period_clause(start: datetime, end: datetime):
    return and_(Memory.created_at >= start, Memory.created_at < end)


def _goal_payload(goals: list[Goal]) -> list[dict[str, object]]:
    return [
        {
            "id": str(goal.id),
            "title": goal.title,
            "life_area": goal.life_area,
            "status": goal.status,
        }
        for goal in goals
    ]


def _memory_titles(memories: list[Memory], *types: str) -> list[str]:
    allowed = set(types)
    return [row.title for row in memories if row.type in allowed][:6]


def _area_counts(memories: list[Memory], tasks: list[Task], goals: list[Goal]) -> list[dict[str, object]]:
    counts = Counter()
    for row in memories:
        if row.life_area:
            counts[row.life_area] += 1
    for row in tasks:
        if row.category:
            counts[row.category] += 1
    for row in goals:
        if row.life_area:
            counts[row.life_area] += 1
    return [{"life_area": area, "count": count} for area, count in counts.most_common()]


async def _period_snapshot(db: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> dict[str, object]:
    today_items = list((await db.execute(
        select(TodayItem)
        .where(TodayItem.user_id == user_id, _period_clause(start, end))
        .order_by(TodayItem.start_time.asc().nulls_last(), TodayItem.created_at.asc())
    )).scalars().all())
    tasks = list((await db.execute(
        select(Task)
        .where(Task.user_id == user_id, Task.created_at >= start, Task.created_at < end)
        .order_by(Task.created_at.desc())
    )).scalars().all())
    meetings = list((await db.execute(
        select(Meeting)
        .where(Meeting.user_id == user_id, Meeting.start_time >= start, Meeting.start_time < end)
        .order_by(Meeting.start_time.asc())
    )).scalars().all())
    memories = list((await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            _memory_period_clause(start, end),
            Memory.user_approved.is_(True),
            Memory.paused.is_(False),
            Memory.approval_status == "approved",
        )
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(80)
    )).scalars().all())
    goals = list((await db.execute(
        select(Goal)
        .where(
            Goal.user_id == user_id,
            or_(Goal.status.in_(["active", "in_progress"]), and_(Goal.updated_at >= start, Goal.updated_at < end)),
        )
        .order_by(Goal.updated_at.desc())
        .limit(12)
    )).scalars().all())
    reflections = list((await db.execute(
        select(Reflection)
        .where(Reflection.user_id == user_id, Reflection.created_at >= start, Reflection.created_at < end)
        .order_by(Reflection.created_at.desc())
        .limit(20)
    )).scalars().all())
    habit_logs = list((await db.execute(
        select(HabitLog)
        .where(HabitLog.user_id == user_id, HabitLog.logged_at >= start, HabitLog.logged_at < end)
    )).scalars().all())
    people = list((await db.execute(
        select(KnowledgeEntity)
        .where(KnowledgeEntity.user_id == user_id, KnowledgeEntity.entity_type.in_(["person", "relationship"]))
        .order_by(KnowledgeEntity.updated_at.desc())
        .limit(8)
    )).scalars().all())

    completed_tasks = len([row for row in tasks if row.status in {"done", "completed"}])
    completed_items = len([row for row in today_items if row.status == "completed"])
    focus_minutes = 0
    for item in today_items:
        if item.type != "focus":
            continue
        metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
        duration = metadata.get("duration_minutes") or metadata.get("actual_minutes") or metadata.get("planned_minutes")
        if isinstance(duration, (int, float)):
            focus_minutes += int(duration)

    positive = len([row for row in memories if row.sentiment == "positive"])
    negative = len([row for row in memories if row.sentiment == "negative"])
    sparse = not any((today_items, tasks, meetings, memories, goals, reflections, habit_logs))

    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "sparse": sparse,
        "summary": {
            "today_items": len(today_items),
            "completed_today_items": completed_items,
            "tasks": len(tasks),
            "completed_tasks": completed_tasks,
            "meetings": len(meetings),
            "memories": len(memories),
            "reflections": len(reflections),
            "habit_logs": len(habit_logs),
            "focus_minutes": focus_minutes,
        },
        "business": {
            "meetings": len(meetings),
            "tasks": len([row for row in tasks if row.category == "business"]),
            "projects_or_wins": _memory_titles(memories, "project", "win", "milestone"),
        },
        "health": {
            "habit_logs": len(habit_logs),
            "signals": [row.title for row in memories if row.life_area == "health"][:5],
        },
        "learning": {
            "signals": [row.title for row in memories if row.life_area == "learning"][:5],
            "tasks": len([row for row in tasks if row.category == "learning"]),
        },
        "relationships": {
            "people": [{"id": str(row.id), "name": row.name} for row in people],
            "relationship_memories": [row.title for row in memories if row.life_area == "relationships"][:5],
        },
        "growth": {
            "positive_signals": positive,
            "negative_signals": negative,
            "wins": _memory_titles(memories, "win", "milestone", "achievement"),
            "lessons": _memory_titles(memories, "lesson", "decision", "emotional_pattern"),
        },
        "goals": _goal_payload(goals),
        "life_area_counts": _area_counts(memories, tasks, goals),
    }


async def generate_weekly_insights(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    start, end = _week_bounds()
    return {"status": "ok", "granularity": "weekly", **await _period_snapshot(db, user_id, start, end)}


async def generate_monthly_insights(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    start, end = _month_bounds()
    return {"status": "ok", "granularity": "monthly", **await _period_snapshot(db, user_id, start, end)}


async def generate_life_area_insights(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    areas = await get_life_area_insights(db, user_id)
    return {
        "status": "ok",
        "areas": areas,
        "sparse": not any(
            (area.get("memory_count") or area.get("task_count") or area.get("goal_count") or area.get("reflection_count"))
            for area in areas
        ),
        "top_areas": sorted(
            areas,
            key=lambda row: (
                int(row.get("memory_count") or 0)
                + int(row.get("task_count") or 0)
                + int(row.get("goal_count") or 0)
                + int(row.get("reflection_count") or 0)
            ),
            reverse=True,
        )[:3],
    }


async def detect_growth_trends(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    start, end = _week_bounds()
    snapshot = await _period_snapshot(db, user_id, start, end)
    growth = snapshot["growth"] if isinstance(snapshot.get("growth"), dict) else {}
    trend = "steady"
    if int(growth.get("positive_signals") or 0) > int(growth.get("negative_signals") or 0):
        trend = "positive"
    elif int(growth.get("negative_signals") or 0) > int(growth.get("positive_signals") or 0):
        trend = "needs_attention"
    return {"status": "ok", "trend": trend, "growth": growth, "period": snapshot["period"]}
