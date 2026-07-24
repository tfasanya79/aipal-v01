from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmotionalState, Goal, Memory, Reflection, Task


def _clamp(value: float) -> int:
    return int(max(0, min(100, round(value))))


async def get_companion_score(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    now = datetime.now(UTC)
    since = now - timedelta(days=14)

    tasks_result = await db.execute(
        select(Task).where(Task.user_id == user_id, Task.updated_at >= since)
    )
    reflections_result = await db.execute(
        select(Reflection).where(Reflection.user_id == user_id, Reflection.created_at >= since)
    )
    memories_result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.created_at >= since,
            Memory.paused.is_(False),
            Memory.user_approved.is_(True),
        )
    )
    emotions_result = await db.execute(
        select(EmotionalState).where(
            EmotionalState.user_id == user_id,
            EmotionalState.created_at >= since,
        )
    )
    goals_result = await db.execute(select(Goal).where(Goal.user_id == user_id))

    tasks = list(tasks_result.scalars().all())
    reflections = list(reflections_result.scalars().all())
    memories = list(memories_result.scalars().all())
    emotions = list(emotions_result.scalars().all())
    goals = list(goals_result.scalars().all())

    total_activity = len(tasks) + len(reflections) + len(memories) + len(emotions)
    if total_activity < 4 and not goals:
        return {
            "overall": None,
            "message": "Not enough data yet.",
        }

    task_total = len(tasks)
    task_done = sum(1 for task in tasks if task.status == "done")
    consistency = _clamp((task_done / task_total) * 100 if task_total else 35)
    task_goal_ratio = (
        sum(1 for task in tasks if task.goal_id is not None) / task_total if task_total else 0.0
    )

    mood_scores = {
        "positive": 8,
        "excited": 9,
        "happy": 8,
        "neutral": 5,
        "frustrated": 3,
        "sad": 2,
        "anxious": 3,
        "drained": 2,
    }
    if emotions:
        energy = 100 - (_clamp(mean(item.intensity or 0 for item in emotions) * 10) - 10)
        energy = _clamp(energy + sum(mood_scores.get(getattr(item, "emotion", ""), 0) for item in emotions) / max(len(emotions), 1))
    else:
        energy = 55

    distinct_areas = {
        (memory.life_area or "").lower()
        for memory in memories
        if memory.life_area
    } | {
        (task.category or "").lower()
        for task in tasks
        if getattr(task, "category", None)
    }
    if not distinct_areas:
        distinct_areas = {(goal.life_area or "").lower() for goal in goals if goal.life_area}
    focus = _clamp(100 - max(0, len(distinct_areas) - 1) * 12 + task_goal_ratio * 20)

    goal_progress_total = 0
    goal_progress_done = 0
    for goal in goals:
        goal_tasks = [task for task in tasks if task.goal_id == goal.id]
        goal_progress_total += len(goal_tasks)
        goal_progress_done += sum(1 for task in goal_tasks if task.status == "done")
    if goal_progress_total:
        goal_progress = _clamp((goal_progress_done / goal_progress_total) * 100)
    else:
        goal_progress = 35 if goals else 0

    reflection_frequency = _clamp((len(reflections) / 4) * 100)

    overall = _clamp(mean([consistency, energy, focus, max(goal_progress, 10), reflection_frequency]))
    explanation_bits = []
    if task_total:
        explanation_bits.append(f"{task_done}/{task_total} tasks completed")
    if reflections:
        explanation_bits.append(f"{len(reflections)} reflections logged")
    if memories:
        explanation_bits.append(f"{len(memories)} memories added")
    if emotions:
        explanation_bits.append(f"{len(emotions)} emotional check-ins")
    explanation_parts = []
    explanation_parts.append("You kept a steady rhythm." if consistency >= 70 else "Your rhythm was a bit uneven this period.")
    if energy < 50:
        explanation_parts.append("Energy looked a little low.")
    elif energy > 70:
        explanation_parts.append("Energy looked healthy.")
    if focus < 55:
        explanation_parts.append("Your attention was spread across a few areas.")
    elif focus > 75:
        explanation_parts.append("You stayed fairly focused on a small set of priorities.")
    explanation = " ".join(explanation_parts)
    return {
        "overall": overall,
        "consistency": consistency,
        "energy": energy,
        "focus": focus,
        "goal_progress": goal_progress,
        "reflection_frequency": reflection_frequency,
        "explanation": explanation.strip(),
        "details": explanation_bits,
    }
