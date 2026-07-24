from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, Memory, Reflection, Task


def _period_range(period: str) -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    if period == "month":
        start = end - timedelta(days=30)
    elif period == "quarter":
        start = end - timedelta(days=90)
    else:
        start = end - timedelta(days=365)
    return start, end


async def get_life_story(db: AsyncSession, user_id: UUID, period: str = "year") -> dict[str, object]:
    start, end = _period_range(period)
    memories = list((await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.created_at >= start, Memory.created_at <= end))).scalars().all())
    reflections = list((await db.execute(select(Reflection).where(Reflection.user_id == user_id, Reflection.created_at >= start, Reflection.created_at <= end))).scalars().all())
    tasks = list((await db.execute(select(Task).where(Task.user_id == user_id, Task.created_at >= start, Task.created_at <= end))).scalars().all())
    goals = list((await db.execute(select(Goal).where(Goal.user_id == user_id))).scalars().all())

    accomplishments = [m.title for m in memories if m.type in {"win", "milestone", "important_event"}][:6]
    if not accomplishments:
        accomplishments = [t.title for t in tasks if t.status == "done"][:6]
    patterns = [m.title for m in memories if m.type in {"recurring_concern", "emotional_pattern", "project"}][:6]
    strengths = [m.title for m in memories if m.type in {"win", "relationship", "person"}][:6]
    growth_summary = [r.summary or r.lessons or "" for r in reflections if (r.summary or r.lessons)][:6]
    summary = "You have been building steadily."
    if goals:
        summary = f"You are building toward {goals[0].title}."
    return {
        "period": period,
        "summary": summary,
        "accomplishments": accomplishments,
        "patterns": patterns,
        "strengths": strengths,
        "growth_summary": growth_summary,
    }


async def get_life_story_accomplishments(db: AsyncSession, user_id: UUID, period: str = "year") -> dict[str, object]:
    story = await get_life_story(db, user_id, period)
    return {"period": story["period"], "summary": story["summary"], "accomplishments": story["accomplishments"]}

