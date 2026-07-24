from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import EmotionalState, Goal, Memory, Reflection, Task

_LIFE_AREAS = ("business", "health", "finance", "learning", "relationships", "spiritual", "personal_growth")

_AREA_HINTS = {
    "business": ("business", "customer", "client", "sales", "buying", "sell", "launch", "demo", "pipeline", "qring", "estate", "investor"),
    "health": ("health", "exercise", "gym", "sleep", "tired", "exhausted", "workout", "diet", "doctor", "burned out"),
    "finance": ("money", "budget", "bank", "salary", "investment", "invoice", "expense", "income", "revenue"),
    "learning": ("learn", "study", "course", "book", "practice", "lesson", "read"),
    "relationships": ("wife", "husband", "partner", "friend", "family", "mentor", "relationship", "spouse"),
    "spiritual": ("prayer", "church", "faith", "god", "bible", "worship", "meditate"),
    "personal_growth": ("confidence", "discipline", "stress", "routine", "growth", "mental", "self", "burned out", "wellbeing"),
}


def _normalise_area(value: str | None) -> str | None:
    if not value:
        return None
    value = value.lower().strip()
    if value == "personal":
        return "personal_growth"
    if value in _LIFE_AREAS:
        return value
    return None


def _classify_text_area(text: str | None) -> tuple[str | None, float]:
    lower = (text or "").lower()
    scores: dict[str, float] = {}
    for area, hints in _AREA_HINTS.items():
        score = 0.0
        for hint in hints:
            if hint in lower:
                score += 1.0
                if " " in hint:
                    score += 0.25
        scores[area] = score
    best_area = max(_LIFE_AREAS, key=lambda area: (scores.get(area, 0.0), -_LIFE_AREAS.index(area)))
    best_score = scores.get(best_area, 0.0)
    if best_score <= 0:
        return None, 0.0
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    confidence = min(1.0, 0.42 + (best_score * 0.16) + max(best_score - second_score, 0.0) * 0.08)
    if confidence < 0.58:
        return None, confidence
    return best_area, confidence


async def get_life_area_insights(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    memory_rows = await db.execute(
        select(Memory.life_area, Memory.importance)
        .where(Memory.user_id == user_id, Memory.paused.is_(False), Memory.user_approved.is_(True))
    )
    task_rows = await db.execute(
        select(Task.category, func.count(Task.id))
        .where(Task.user_id == user_id)
        .group_by(Task.category)
    )
    goal_rows = await db.execute(
        select(Goal.life_area, func.count(Goal.id))
        .where(Goal.user_id == user_id)
        .group_by(Goal.life_area)
    )
    reflection_rows = await db.execute(
        select(Reflection.mood, Reflection.goal_id, Reflection.type, Reflection.summary, Goal.life_area)
        .join(Goal, Goal.id == Reflection.goal_id, isouter=True)
        .where(Reflection.user_id == user_id)
    )
    emotion_rows = await db.execute(
        select(EmotionalState.emotion, EmotionalState.intensity, EmotionalState.context)
        .where(EmotionalState.user_id == user_id)
    )

    memory_counts = Counter()
    memory_strengths: dict[str, list[float]] = defaultdict(list)
    for area, importance in memory_rows.all():
        area_name = _normalise_area(str(area) if area else None)
        if not area_name:
            continue
        memory_counts[area_name] += 1
        memory_strengths[area_name].append(float(importance or 0))

    task_counts = Counter()
    for category, count in task_rows.all():
        area_name = _normalise_area(str(category) if category else None)
        if not area_name:
            continue
        task_counts[area_name] += int(count or 0)

    goal_counts = Counter()
    for area, count in goal_rows.all():
        area_name = _normalise_area(str(area) if area else None)
        if not area_name:
            continue
        goal_counts[area_name] += int(count or 0)

    reflection_counts = Counter()
    for mood, goal_id, type_, summary, goal_area in reflection_rows.all():
        area_name = _normalise_area(str(goal_area) if goal_area else None)
        if area_name is None:
            area_name, confidence = _classify_text_area(summary or mood)
            if confidence < 0.62:
                area_name = None
        if area_name:
            reflection_counts[area_name] += 1
        if type_ == "weekly" and summary:
            reflection_counts["personal_growth"] += 0

    emotional_strengths: dict[str, list[float]] = defaultdict(list)
    for emotion, intensity, context in emotion_rows.all():
        text = f"{emotion or ''} {context or ''}".lower()
        matched, confidence = _classify_text_area(text)
        if confidence < 0.58:
            matched = None
        if matched is not None:
            emotional_strengths[matched].append(float(intensity or 0))

    total_activity = sum(memory_counts.values()) + sum(task_counts.values()) + sum(goal_counts.values()) + sum(reflection_counts.values())
    avg_activity = total_activity / len(_LIFE_AREAS) if _LIFE_AREAS else 0

    areas: list[dict[str, object]] = []
    for area in _LIFE_AREAS:
        activity = memory_counts[area] + task_counts[area] + goal_counts[area] + reflection_counts[area]
        avg_emotion = mean(memory_strengths[area]) if memory_strengths[area] else (
            mean(emotional_strengths[area]) if emotional_strengths[area] else 0.0
        )
        if avg_activity:
            distance = abs(activity - avg_activity) / avg_activity
        else:
            distance = 0.0
        balance = int(max(0, min(100, round(100 - (distance * 55)))))
        if activity == 0:
            balance = max(balance - 12, 0)
        if avg_emotion:
            balance = max(min(balance + int((avg_emotion - 5) * 2), 100), 0)
        areas.append(
            {
                "life_area": area,
                "memory_count": int(memory_counts[area]),
                "task_count": int(task_counts[area]),
                "goal_count": int(goal_counts[area]),
                "reflection_count": int(reflection_counts[area]),
                "average_emotion_intensity": round(avg_emotion, 2),
                "balance_score": balance,
            }
        )

    areas.sort(key=lambda item: (item["balance_score"], item["memory_count"] + item["task_count"] + item["goal_count"]), reverse=True)
    return areas
