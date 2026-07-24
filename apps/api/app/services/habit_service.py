from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Habit, HabitLog

_HABIT_HINTS = {
    "exercise": ("exercise", "gym", "workout", "run", "running"),
    "reading": ("reading", "read", "book"),
    "prayer": ("prayer", "praying", "pray"),
    "meditation": ("meditation", "meditate"),
    "learning": ("learn", "learning", "study", "course"),
    "sales calls": ("sales call", "sales calls", "cold call", "calls"),
}


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def detect_habit_signal(message: str, context: str | None = None) -> dict[str, object] | None:
    text = f"{message} {context or ''}".lower()
    for name, hints in _HABIT_HINTS.items():
        count = sum(1 for hint in hints if hint in text)
        if count == 0:
            continue
        mention_count = sum(text.count(hint) for hint in hints)
        if mention_count >= 2 or any(word in text for word in ("again", "consistent", "every", "routinely", "daily", "weekly")):
            life_area = "health"
            if name in {"prayer", "meditation"}:
                life_area = "spiritual"
            elif name in {"learning"}:
                life_area = "learning"
            elif name in {"sales calls"}:
                life_area = "business"
            return {
                "name": name,
                "life_area": life_area,
                "frequency": "daily" if name != "sales calls" else "weekly",
                "confidence": 0.8 if mention_count >= 2 else 0.65,
            }
    return None


async def create_habit(
    db: AsyncSession,
    user_id: UUID,
    name: str,
    life_area: str | None = None,
    frequency: str = "daily",
    target_count: int = 1,
) -> Habit:
    habit = Habit(
        user_id=user_id,
        name=name.strip(),
        life_area=life_area,
        frequency=frequency,
        target_count=target_count,
        status="active",
    )
    db.add(habit)
    await db.commit()
    await db.refresh(habit)
    return habit


async def log_habit(
    db: AsyncSession,
    user_id: UUID,
    habit_id: UUID,
    value: int = 1,
    note: str | None = None,
    source: str = "manual",
) -> HabitLog | None:
    result = await db.execute(
        select(Habit).where(Habit.user_id == user_id, Habit.id == habit_id)
    )
    habit = result.scalar_one_or_none()
    if habit is None:
        return None
    log = HabitLog(
        user_id=user_id,
        habit_id=habit_id,
        value=value,
        note=note,
        source=source,
        logged_at=datetime.now(UTC),
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


async def list_habits(db: AsyncSession, user_id: UUID) -> list[Habit]:
    result = await db.execute(
        select(Habit).where(Habit.user_id == user_id).order_by(Habit.created_at.desc())
    )
    return list(result.scalars().all())


def _streak_for_logs(logs: list[HabitLog]) -> int:
    if not logs:
        return 0
    days = sorted({log.logged_at.date() for log in logs}, reverse=True)
    streak = 0
    expected = days[0]
    for day in days:
        if day == expected:
            streak += 1
            expected = expected - timedelta(days=1)
        else:
            break
    return streak


async def summarize_habits(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    habits = await list_habits(db, user_id)
    if not habits:
        return {"habits": [], "streaks": {}, "weekly_consistency": {}, "suggestions": []}

    logs_result = await db.execute(
        select(HabitLog)
        .where(HabitLog.user_id == user_id, HabitLog.logged_at >= datetime.now(UTC) - timedelta(days=30))
        .order_by(HabitLog.logged_at.desc())
    )
    logs = list(logs_result.scalars().all())
    logs_by_habit: dict[UUID, list[HabitLog]] = defaultdict(list)
    for log in logs:
        logs_by_habit[log.habit_id].append(log)

    streaks = {str(habit.id): _streak_for_logs(logs_by_habit.get(habit.id, [])) for habit in habits}
    weekly_consistency = {}
    now = datetime.now(UTC)
    week_start = now - timedelta(days=6)
    week_start_naive = _naive_utc(week_start)
    weekly_logs = [log for log in logs if _naive_utc(log.logged_at) >= week_start_naive]
    week_counts = Counter(log.habit_id for log in weekly_logs)
    for habit in habits:
        target = max(habit.target_count, 1)
        consistency = min(100.0, round((week_counts.get(habit.id, 0) / (target * 7)) * 100, 2))
        weekly_consistency[str(habit.id)] = consistency

    suggestions = []
    for habit in habits:
        if streaks[str(habit.id)] >= 2:
            suggestions.append(f"Nice consistency with {habit.name}.")
        elif week_counts.get(habit.id, 0) == 0:
            suggestions.append(f"You have not logged {habit.name} recently.")

    return {
        "habits": [
            {
                "id": habit.id,
                "name": habit.name,
                "life_area": habit.life_area,
                "frequency": habit.frequency,
                "target_count": habit.target_count,
                "status": habit.status,
                "created_at": habit.created_at,
                "updated_at": habit.updated_at,
            }
            for habit in habits
        ],
        "streaks": streaks,
        "weekly_consistency": weekly_consistency,
        "suggestions": suggestions[:6],
    }
