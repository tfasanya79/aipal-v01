from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal, Habit, KnowledgeEntity, Memory, Reflection, Task

LIFE_AREAS = (
    "business",
    "health",
    "finance",
    "learning",
    "relationships",
    "spiritual",
    "personal_growth",
)

AREA_LABELS = {
    "business": "Business",
    "health": "Health",
    "finance": "Finance",
    "learning": "Learning",
    "relationships": "Relationships",
    "spiritual": "Spiritual",
    "personal_growth": "Personal Growth",
}

WIN_TYPES = {"win", "achievement", "milestone"}
CHALLENGE_TYPES = {"concern", "blocker", "setback", "challenge"}

AREA_HINTS = {
    "business": (
        "business",
        "customer",
        "client",
        "sales",
        "sell",
        "demo",
        "qring",
        "estate",
        "investor",
        "proposal",
        "pitch",
        "startup",
        "meeting",
    ),
    "health": ("health", "exercise", "gym", "sleep", "workout", "diet", "doctor", "fitness", "tired", "rest"),
    "finance": ("money", "budget", "bank", "invoice", "expense", "income", "revenue", "finance", "pay", "payment"),
    "learning": ("learn", "study", "course", "book", "practice", "lesson", "read", "research"),
    "relationships": ("wife", "husband", "partner", "friend", "family", "mentor", "relationship", "stephen", "chairman"),
    "spiritual": ("prayer", "church", "faith", "god", "bible", "worship", "meditate", "spiritual"),
    "personal_growth": ("confidence", "discipline", "stress", "routine", "growth", "mental", "self", "wellbeing"),
}


def normalise_life_area(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.lower().strip().replace("-", "_").replace(" ", "_")
    if cleaned == "personal":
        return "personal_growth"
    if cleaned in LIFE_AREAS:
        return cleaned
    return None


def _life_area_scores(*parts: object) -> dict[str, float]:
    text = " ".join(str(part or "") for part in parts).lower()
    if not text.strip():
        return {}
    scores: dict[str, float] = {}
    for area, hints in AREA_HINTS.items():
        score = 0.0
        for hint in hints:
            if hint in text:
                score += 1.0
                if " " in hint:
                    score += 0.25
        scores[area] = score
    return scores


def candidate_life_areas_from_text(*parts: object, limit: int = 2) -> list[str]:
    scores = _life_area_scores(*parts)
    ranked = sorted(
        ((area, score) for area, score in scores.items() if score > 0),
        key=lambda item: (item[1], -LIFE_AREAS.index(item[0])),
        reverse=True,
    )
    return [area for area, _ in ranked[:limit]]


def classify_life_area_from_text(*parts: object) -> str | None:
    scores = _life_area_scores(*parts)
    if not scores:
        return None
    best_area = max(LIFE_AREAS, key=lambda area: (scores.get(area, 0.0), -LIFE_AREAS.index(area)))
    best_score = scores.get(best_area, 0.0)
    if best_score <= 0:
        return None
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    if best_score < 1.0 or best_score - second_score < 0.25:
        return None
    return best_area


def _memory_area(memory: Memory) -> str | None:
    return normalise_life_area(memory.life_area) or classify_life_area_from_text(
        memory.title,
        memory.content,
        memory.type,
        memory.sentiment,
    )


def _goal_area(goal: Goal) -> str | None:
    return normalise_life_area(goal.life_area) or classify_life_area_from_text(goal.title, goal.description)


def _task_area(task: Task, goal_area: str | None = None) -> str | None:
    return normalise_life_area(task.category) or goal_area or classify_life_area_from_text(task.title, task.notes)


def _habit_area(habit: Habit) -> str | None:
    return normalise_life_area(habit.life_area) or classify_life_area_from_text(habit.name)


def _reflection_area(reflection: Reflection, goal_area: str | None = None) -> str | None:
    return goal_area or classify_life_area_from_text(
        reflection.summary,
        reflection.wins,
        reflection.challenges,
        reflection.lessons,
        reflection.mood,
        reflection.type,
    )


def _memory_candidate_areas(memory: Memory) -> list[str]:
    if _memory_area(memory):
        return []
    return candidate_life_areas_from_text(memory.title, memory.content, memory.type, memory.sentiment)


def _goal_candidate_areas(goal: Goal) -> list[str]:
    if _goal_area(goal):
        return []
    return candidate_life_areas_from_text(goal.title, goal.description)


def _task_candidate_areas(task: Task, goal_area: str | None = None) -> list[str]:
    if _task_area(task, goal_area):
        return []
    return candidate_life_areas_from_text(task.title, task.notes)


def _habit_candidate_areas(habit: Habit) -> list[str]:
    if _habit_area(habit):
        return []
    return candidate_life_areas_from_text(habit.name)


def _reflection_candidate_areas(reflection: Reflection, goal_area: str | None = None) -> list[str]:
    if _reflection_area(reflection, goal_area):
        return []
    return candidate_life_areas_from_text(
        reflection.summary,
        reflection.wins,
        reflection.challenges,
        reflection.lessons,
        reflection.mood,
        reflection.type,
    )


def _memory_visible_filter(now: datetime):
    return (
        Memory.paused.is_(False),
        Memory.user_approved.is_(True),
        Memory.approval_status == "approved",
        (Memory.expires_at.is_(None) | (Memory.expires_at > now)),
        Memory.memory_scope != "temporary",
    )


def _progress_score(*counts: int) -> int:
    activity = sum(max(0, count) for count in counts)
    if activity <= 0:
        return 0
    return min(100, 18 + activity * 12)


def _memory_item(memory: Memory) -> dict[str, object]:
    return {
        "id": str(memory.id),
        "title": memory.title,
        "type": memory.type,
        "importance": memory.importance,
        "created_at": memory.created_at,
    }


def _goal_item(goal: Goal) -> dict[str, object]:
    return {
        "id": str(goal.id),
        "title": goal.title,
        "status": goal.status,
        "priority": goal.priority,
        "target_date": goal.target_date,
    }


def _task_item(task: Task) -> dict[str, object]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_at": task.due_at,
    }


def _habit_item(habit: Habit) -> dict[str, object]:
    return {
        "id": str(habit.id),
        "name": habit.name,
        "frequency": habit.frequency,
        "status": habit.status,
    }


def _reflection_item(reflection: Reflection) -> dict[str, object]:
    return {
        "id": str(reflection.id),
        "type": reflection.type,
        "mood": reflection.mood,
        "summary": reflection.summary,
        "created_at": reflection.created_at,
    }


def _candidate_item(kind: str, item: dict[str, object]) -> dict[str, object]:
    return {"kind": kind, "confidence": "needs_review", **item}


async def _load_life_map_rows(db: AsyncSession, user_id: UUID) -> dict[str, list]:
    now = datetime.now(timezone.utc)
    memory_rows = await db.execute(
        select(Memory)
        .where(Memory.user_id == user_id, *_memory_visible_filter(now))
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
    )
    goal_rows = await db.execute(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at.desc()))
    task_rows = await db.execute(select(Task).where(Task.user_id == user_id).order_by(Task.created_at.desc()))
    habit_rows = await db.execute(select(Habit).where(Habit.user_id == user_id).order_by(Habit.created_at.desc()))
    reflection_rows = await db.execute(
        select(Reflection, Goal.life_area)
        .join(Goal, Goal.id == Reflection.goal_id, isouter=True)
        .where(Reflection.user_id == user_id)
        .order_by(Reflection.created_at.desc())
    )
    people_rows = await db.execute(
        select(KnowledgeEntity)
        .where(
            KnowledgeEntity.user_id == user_id,
            KnowledgeEntity.entity_type.in_(("person", "relationship")),
        )
        .order_by(KnowledgeEntity.updated_at.desc())
    )
    return {
        "memories": list(memory_rows.scalars().all()),
        "goals": list(goal_rows.scalars().all()),
        "tasks": list(task_rows.scalars().all()),
        "habits": list(habit_rows.scalars().all()),
        "reflections": list(reflection_rows.all()),
        "people": list(people_rows.scalars().all()),
    }


def _build_area_payload(area: str, rows: dict[str, list], detail: bool = False) -> dict[str, object]:
    goal_area_by_id = {goal.id: _goal_area(goal) for goal in rows["goals"]}
    goals = [goal for goal in rows["goals"] if goal_area_by_id.get(goal.id) == area]
    memories = [memory for memory in rows["memories"] if _memory_area(memory) == area]
    tasks = [
        task
        for task in rows["tasks"]
        if _task_area(task, goal_area_by_id.get(task.goal_id) if task.goal_id is not None else None) == area
    ]
    habits = [habit for habit in rows["habits"] if _habit_area(habit) == area]
    reflections = [
        reflection
        for reflection, goal_area in rows["reflections"]
        if _reflection_area(reflection, normalise_life_area(goal_area)) == area
    ]
    suggested_items: list[dict[str, object]] = []
    suggested_items.extend(
        _candidate_item("memory", _memory_item(memory))
        for memory in rows["memories"]
        if area in _memory_candidate_areas(memory)
    )
    suggested_items.extend(
        _candidate_item("goal", _goal_item(goal))
        for goal in rows["goals"]
        if area in _goal_candidate_areas(goal)
    )
    suggested_items.extend(
        _candidate_item("task", _task_item(task))
        for task in rows["tasks"]
        if area in _task_candidate_areas(task, goal_area_by_id.get(task.goal_id) if task.goal_id is not None else None)
    )
    suggested_items.extend(
        _candidate_item("habit", _habit_item(habit))
        for habit in rows["habits"]
        if area in _habit_candidate_areas(habit)
    )
    suggested_items.extend(
        _candidate_item("reflection", _reflection_item(reflection))
        for reflection, goal_area in rows["reflections"]
        if area in _reflection_candidate_areas(reflection, normalise_life_area(goal_area))
    )
    suggested_items = suggested_items[:8]

    wins = [memory for memory in memories if (memory.type or "").lower() in WIN_TYPES or (memory.sentiment or "") == "positive"]
    challenges = [
        memory
        for memory in memories
        if (memory.type or "").lower() in CHALLENGE_TYPES or (memory.sentiment or "") in {"concern", "negative"}
    ]
    people_count = len(rows["people"]) if area == "relationships" else 0
    progress = _progress_score(len(memories), len(goals), len(tasks), len(habits), len(reflections), people_count)

    top_items = []
    top_items.extend({"kind": "memory", **_memory_item(memory)} for memory in memories[:3])
    top_items.extend({"kind": "goal", **_goal_item(goal)} for goal in goals[:2])
    top_items = top_items[:5]

    payload: dict[str, object] = {
        "life_area": area,
        "label": AREA_LABELS[area],
        "progress": progress,
        "memory_count": len(memories),
        "goal_count": len(goals),
        "task_count": len(tasks),
        "habit_count": len(habits),
        "reflection_count": len(reflections),
        "relationship_count": people_count,
        "win_count": len(wins),
        "challenge_count": len(challenges),
        "suggested_count": len(suggested_items),
        "top_items": top_items,
    }
    if detail:
        payload.update(
            {
                "memories": [_memory_item(memory) for memory in memories[:20]],
                "goals": [_goal_item(goal) for goal in goals[:20]],
                "tasks": [_task_item(task) for task in tasks[:30]],
                "habits": [_habit_item(habit) for habit in habits[:20]],
                "reflections": [_reflection_item(reflection) for reflection in reflections[:20]],
                "wins": [_memory_item(memory) for memory in wins[:10]],
                "challenges": [_memory_item(memory) for memory in challenges[:10]],
                "suggested_items": suggested_items,
                "patterns": _build_patterns(area, memories, goals, tasks, habits, reflections, people_count),
            }
        )
    return payload


def _build_patterns(
    area: str,
    memories: list[Memory],
    goals: list[Goal],
    tasks: list[Task],
    habits: list[Habit],
    reflections: list[Reflection],
    people_count: int,
) -> list[str]:
    patterns: list[str] = []
    if goals:
        patterns.append(f"{len(goals)} goal{'s' if len(goals) != 1 else ''} linked to this area.")
    open_tasks = [task for task in tasks if task.status not in {"done", "completed", "cancelled"}]
    if open_tasks:
        patterns.append(f"{len(open_tasks)} open task{'s' if len(open_tasks) != 1 else ''} still need attention.")
    if habits:
        patterns.append(f"{len(habits)} active habit{'s' if len(habits) != 1 else ''} support this area.")
    if memories:
        sentiment_counts = Counter((memory.sentiment or "neutral") for memory in memories)
        dominant = sentiment_counts.most_common(1)[0][0]
        patterns.append(f"Most saved memories here are marked as {dominant}.")
    if area == "relationships" and people_count:
        patterns.append(f"{people_count} important people are connected to your relationship map.")
    if reflections:
        patterns.append(f"{len(reflections)} reflection{'s' if len(reflections) != 1 else ''} mention this area.")
    return patterns


async def get_life_map(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    rows = await _load_life_map_rows(db, user_id)
    areas = [_build_area_payload(area, rows) for area in LIFE_AREAS]
    total_counts = sum(
        int(area["memory_count"])
        + int(area["goal_count"])
        + int(area["task_count"])
        + int(area["habit_count"])
        + int(area["reflection_count"])
        + int(area["relationship_count"])
        for area in areas
    )
    suggested_counts = sum(int(area["suggested_count"]) for area in areas)
    return {
        "status": "ok",
        "areas": areas,
        "sparse": total_counts == 0 and suggested_counts == 0,
        "total_activity": total_counts,
        "suggested_activity": suggested_counts,
    }


async def get_life_area_detail(db: AsyncSession, user_id: UUID, area: str) -> dict[str, object] | None:
    normalised = normalise_life_area(area)
    if normalised is None:
        return None
    rows = await _load_life_map_rows(db, user_id)
    payload = _build_area_payload(normalised, rows, detail=True)
    payload["status"] = "ok"
    return payload
