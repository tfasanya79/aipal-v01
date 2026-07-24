from __future__ import annotations

from collections import Counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, Habit, Memory, Reflection, EmotionalState, CoachDecision


async def get_understanding_profile(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    memories = list(
        (await db.execute(
            select(Memory).where(Memory.user_id == user_id, Memory.user_approved.is_(True), Memory.paused.is_(False)).order_by(Memory.created_at.desc()).limit(80)
        )).scalars().all()
    )
    goals = list((await db.execute(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at.desc()).limit(20))).scalars().all())
    reflections = list((await db.execute(select(Reflection).where(Reflection.user_id == user_id).order_by(Reflection.created_at.desc()).limit(20))).scalars().all())
    habits = list((await db.execute(select(Habit).where(Habit.user_id == user_id).order_by(Habit.created_at.desc()).limit(20))).scalars().all())
    decisions = list((await db.execute(select(CoachDecision).where(CoachDecision.user_id == user_id).order_by(CoachDecision.created_at.desc()).limit(20))).scalars().all())
    emotions = list((await db.execute(select(EmotionalState).where(EmotionalState.user_id == user_id).order_by(EmotionalState.created_at.desc()).limit(30))).scalars().all())

    if not any([memories, goals, reflections, habits, decisions, emotions]):
        return {
            "identity_summary": "Not enough data yet to build a full profile.",
            "cares_about": [],
            "motivators": [],
            "fears_or_blockers": [],
            "current_builds": [],
            "recurring_patterns": [],
            "strengths": [],
            "growth_edges": [],
        }

    memory_topics = Counter((memory.life_area or "general") for memory in memories)
    care_topics = [key for key, _count in memory_topics.most_common(4) if key != "general"]
    motivators = []
    if any(goal.status == "active" for goal in goals):
        motivators.append("progress on active goals")
    if any(habit.status == "active" for habit in habits):
        motivators.append("consistency and routines")
    blockers = []
    if any(m.type in {"recurring_concern", "failure"} for m in memories):
        blockers.append("sales or progress friction")
    if any(e.emotion in {"anxious", "frustrated", "drained"} for e in emotions):
        blockers.append("emotional pressure")
    current_builds = [goal.title for goal in goals[:5]]
    patterns = [memory.title for memory in memories if memory.type in {"recurring_concern", "important_event", "emotional_pattern"}][:5]
    strengths = [item for item in [
        "follow-through",
        "relationship awareness",
        "business focus",
        "reflection",
        "habit consistency" if habits else None,
    ] if item]
    growth_edges = [item for item in [
        "delegation",
        "consistency under pressure",
        "balancing business and recovery",
    ] if item]
    return {
        "identity_summary": "You seem to be a builder who cares about progress, follow-through, and keeping relationships in view.",
        "cares_about": care_topics,
        "motivators": motivators,
        "fears_or_blockers": blockers,
        "current_builds": current_builds,
        "recurring_patterns": patterns,
        "strengths": strengths,
        "growth_edges": growth_edges,
    }

