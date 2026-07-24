from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmotionalState, Goal, Memory, Reflection, Task
from .life_area_service import get_life_area_insights


def _bullet_join(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items if item)


def _listify(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [part.strip() for part in value.replace(";", "\n").splitlines()]
    return [part for part in parts if part]


def _humanize_fragment(fragment: str | None) -> str:
    text = (fragment or "").strip().rstrip(".")
    if not text:
        return ""
    lower = text.lower()
    words = lower.split()
    if not words:
        return ""
    if words[0] == "keep" and len(words) > 1:
        text = f"kept {' '.join(words[1:])}"
    elif words[0] in {
        "felt",
        "was",
        "were",
        "had",
        "kept",
        "made",
        "got",
        "closed",
        "finished",
        "booked",
        "missed",
        "lost",
        "won",
        "launched",
        "signed",
        "shipped",
        "started",
        "worked",
        "learned",
        "prayed",
        "improved",
        "increased",
    }:
        text = lower
    elif len(words) <= 3:
        text = f"had a {lower}"
    else:
        text = lower
    return f"You {text[0].upper() + text[1:]}." if text else ""


def _first_memory_text(memories: list[Memory], types: set[str]) -> str | None:
    for memory in memories:
        if memory.type in types:
            candidate = memory.title or memory.content
            if candidate:
                return candidate
    return None


def _trend_direction(emotions: list[EmotionalState]) -> str | None:
    if len(emotions) < 4:
        return None
    midpoint = max(len(emotions) // 2, 1)
    first_half = [int(item.intensity or 0) for item in emotions[:midpoint]]
    second_half = [int(item.intensity or 0) for item in emotions[midpoint:]]
    if not first_half or not second_half:
        return None
    first_avg = mean(first_half)
    second_avg = mean(second_half)
    if second_avg >= first_avg + 0.75:
        return "moved up"
    if second_avg <= first_avg - 0.75:
        return "dipped"
    return "held steady"


async def generate_weekly_review(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    now = datetime.now(UTC)
    since = now - timedelta(days=7)

    memories_result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.created_at >= since,
            Memory.paused.is_(False),
            Memory.user_approved.is_(True),
        )
        .order_by(Memory.created_at.desc())
    )
    reflections_result = await db.execute(
        select(Reflection).where(
            Reflection.user_id == user_id,
            Reflection.created_at >= since,
        )
        .order_by(Reflection.created_at.desc())
    )
    tasks_result = await db.execute(
        select(Task).where(Task.user_id == user_id, Task.updated_at >= since)
    )
    goals_result = await db.execute(
        select(Goal).where(Goal.user_id == user_id)
    )
    emotions_result = await db.execute(
        select(EmotionalState).where(
            EmotionalState.user_id == user_id,
            EmotionalState.created_at >= since,
        )
        .order_by(EmotionalState.created_at.asc())
    )

    memories = list(memories_result.scalars().all())
    reflections = list(reflections_result.scalars().all())
    tasks = list(tasks_result.scalars().all())
    goals = list(goals_result.scalars().all())
    emotions = list(emotions_result.scalars().all())
    area_insights = await get_life_area_insights(db, user_id)

    wins = [_humanize_fragment(m.title or m.content) for m in memories if m.type in {"win", "milestone"}][:6]
    challenges = [_humanize_fragment(m.title or m.content) for m in memories if m.type in {"failure", "recurring_concern", "challenge"}][:6]
    lessons = [_humanize_fragment(m.title or m.content) for m in memories if m.type in {"decision", "reflection", "emotional_pattern"}][:6]

    if not wins:
        wins = [_humanize_fragment(item) for r in reflections for item in _listify(r.wins)][:3]
    if not challenges:
        challenges = [_humanize_fragment(item) for r in reflections for item in _listify(r.challenges)][:3]
    if not lessons:
        lessons = [_humanize_fragment(item) for r in reflections for item in _listify(r.lessons)][:3]

    mood_by_day: dict[str, list[int]] = defaultdict(list)
    for item in emotions:
        mood_by_day[item.created_at.date().isoformat()].append(int(item.intensity or 0))
    mood_trend = {
        "days": [
            {"date": day, "average_intensity": round(mean(intensities), 2), "count": len(intensities)}
            for day, intensities in sorted(mood_by_day.items())
        ]
    }
    trend_direction = _trend_direction(emotions)

    goal_progress: list[dict[str, object]] = []
    task_counts_by_goal = Counter(task.goal_id for task in tasks if task.goal_id is not None)
    completed_by_goal = Counter(task.goal_id for task in tasks if task.goal_id is not None and task.status == "done")
    for goal in goals:
        total = task_counts_by_goal.get(goal.id, 0)
        completed = completed_by_goal.get(goal.id, 0)
        progress = int(round((completed / total) * 100)) if total else (100 if goal.status == "done" else 0)
        goal_progress.append(
            {
                "goal_id": str(goal.id),
                "title": goal.title,
                "life_area": goal.life_area,
                "status": goal.status,
                "progress": progress,
            }
        )

    life_area_balance = {item["life_area"]: item for item in area_insights}
    recommended_focus = [item["life_area"] for item in sorted(area_insights, key=lambda x: x["balance_score"])[:3]]
    focus_project = _first_memory_text(
        memories,
        {"project", "important_event", "win", "milestone"},
    )
    top_area = max(area_insights, key=lambda item: (item["balance_score"], item["memory_count"] + item["task_count"] + item["goal_count"]), default=None)
    summary_parts = []
    if focus_project:
        summary_parts.append(f"You made meaningful progress on {focus_project}.")
    if wins:
        summary_parts.append(wins[0])
    if challenges:
        summary_parts.append(challenges[0])
    if lessons:
        summary_parts.append(lessons[0])
    if trend_direction == "dipped":
        summary_parts.append("Your energy dipped a bit toward the end of the week.")
    elif trend_direction == "moved up":
        summary_parts.append("Your energy looked steadier as the week went on.")
    if top_area and top_area["balance_score"] < 70:
        summary_parts.append(f"Your {top_area['life_area']} area still looks a little stretched.")
    summary = " ".join(summary_parts) or "A quiet week with limited data."
    score = {
        "wins": len(wins),
        "challenges": len(challenges),
        "lessons": len(lessons),
        "reflections": len(reflections),
        "tasks": len(tasks),
        "emotions": len(emotions),
    }
    weekly = Reflection(
        user_id=user_id,
        goal_id=None,
        type="weekly",
        wins=_bullet_join(wins) or None,
        challenges=_bullet_join(challenges) or None,
        lessons=_bullet_join(lessons) or None,
        mood=mood_trend["days"][-1]["date"] if mood_trend["days"] else None,
        summary=summary,
        metadata_json={
            "generated_at": now.isoformat(),
            "mood_trend": mood_trend,
            "goal_progress": goal_progress,
            "life_area_balance": life_area_balance,
            "recommended_focus": recommended_focus,
        },
        score=score,
    )
    db.add(weekly)
    await db.commit()
    await db.refresh(weekly)
    return {
        "id": str(weekly.id),
        "type": weekly.type,
        "wins": wins,
        "challenges": challenges,
        "lessons": lessons,
        "mood_trend": mood_trend,
        "goal_progress": goal_progress,
        "life_area_balance": life_area_balance,
        "recommended_focus": recommended_focus,
        "summary": summary,
        "score": score,
        "metadata": weekly.metadata_json,
        "created_at": weekly.created_at,
    }


async def latest_weekly_review(db: AsyncSession, user_id: UUID) -> dict[str, object] | None:
    result = await db.execute(
        select(Reflection)
        .where(Reflection.user_id == user_id, Reflection.type == "weekly")
        .order_by(Reflection.created_at.desc())
        .limit(1)
    )
    weekly = result.scalar_one_or_none()
    if weekly is None:
        return None
    metadata = weekly.metadata_json if isinstance(weekly.metadata_json, dict) else {}
    score = weekly.score if isinstance(weekly.score, dict) else weekly.score
    return {
        "id": str(weekly.id),
        "type": weekly.type,
        "wins": _listify(weekly.wins),
        "challenges": _listify(weekly.challenges),
        "lessons": _listify(weekly.lessons),
        "mood_trend": metadata.get("mood_trend", {}),
        "goal_progress": metadata.get("goal_progress", []),
        "life_area_balance": metadata.get("life_area_balance", {}),
        "recommended_focus": metadata.get("recommended_focus", []),
        "summary": weekly.summary,
        "score": score,
        "metadata": metadata,
        "created_at": weekly.created_at,
    }
