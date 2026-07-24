from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AccountabilitySnapshot, Habit, HabitLog, Memory, Task
from .goal_service import list_active_goals


def _period_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    period_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    period_end = datetime.combine(end, datetime.max.time().replace(microsecond=0), tzinfo=UTC)
    return period_start, period_end


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


async def _task_summary(db: AsyncSession, user_id: UUID, start: date, end: date) -> dict[str, object]:
    period_start, period_end = _period_bounds(start, end)
    result = await db.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.created_at >= period_start,
            Task.created_at <= period_end,
        )
    )
    tasks = list(result.scalars().all())
    done = [task for task in tasks if task.status == "done"]
    open_tasks = [task for task in tasks if task.status != "done"]
    period_end_naive = _naive_utc(period_end)
    overdue = [
        task
        for task in tasks
        if task.due_at is not None
        and period_end_naive is not None
        and _naive_utc(task.due_at) is not None
        and _naive_utc(task.due_at) <= period_end_naive
        and task.status != "done"
    ]
    return {
        "created": len(tasks),
        "done": len(done),
        "open": len(open_tasks),
        "overdue": len(overdue),
        "top_open": [task.title for task in open_tasks[:5]],
    }


async def _goal_summary(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    goals = await list_active_goals(db, user_id)
    return {
        "active_goals": len(goals),
        "goals": [
            {
                "id": str(goal.id),
                "title": goal.title,
                "life_area": goal.life_area,
                "status": goal.status,
            }
            for goal in goals[:8]
        ],
    }


async def _habit_summary(db: AsyncSession, user_id: UUID, start: date, end: date) -> dict[str, object]:
    period_start, period_end = _period_bounds(start, end)
    habits_result = await db.execute(
        select(Habit).where(Habit.user_id == user_id).order_by(Habit.created_at.desc())
    )
    habits = list(habits_result.scalars().all())
    logs_result = await db.execute(
        select(HabitLog).where(
            HabitLog.user_id == user_id,
            HabitLog.logged_at >= period_start,
            HabitLog.logged_at <= period_end,
        )
    )
    logs = list(logs_result.scalars().all())
    logs_by_habit = Counter(log.habit_id for log in logs)
    streaks = {}
    for habit in habits:
        streaks[str(habit.id)] = int(logs_by_habit.get(habit.id, 0))
    return {
        "habits": [
            {
                "id": str(habit.id),
                "name": habit.name,
                "life_area": habit.life_area,
                "frequency": habit.frequency,
                "target_count": habit.target_count,
                "status": habit.status,
            }
            for habit in habits[:8]
        ],
        "logs": len(logs),
        "streaks": streaks,
    }


async def _blockers(db: AsyncSession, user_id: UUID, start: date, end: date) -> list[str]:
    period_start, period_end = _period_bounds(start, end)
    result = await db.execute(
        select(Task.title).where(
            Task.user_id == user_id,
            Task.status != "done",
            Task.due_at.is_not(None),
            Task.due_at >= period_start,
            Task.due_at <= period_end,
        )
    )
    blockers = [row[0] for row in result.all()]
    if not blockers:
        memory_rows = await db.execute(
            select(Memory.title).where(
                Memory.user_id == user_id,
                Memory.created_at >= period_start,
                Memory.created_at <= period_end,
                Memory.type.in_(["failure", "recurring_concern"]),
            )
        )
        blockers = [row[0] for row in memory_rows.all()]
    return blockers[:8]


def _snapshot_score(tasks_summary: dict[str, object], habits_summary: dict[str, object], goals_summary: dict[str, object], blockers: list[str]) -> float:
    task_done = int(tasks_summary.get("done", 0) or 0)
    task_open = int(tasks_summary.get("open", 0) or 0)
    habit_logs = int(habits_summary.get("logs", 0) or 0)
    active_goals = int(goals_summary.get("active_goals", 0) or 0)
    base = 40 + min(task_done * 8, 25) + min(habit_logs * 2, 15) + min(active_goals * 4, 20)
    base -= min(task_open * 2, 10)
    base -= min(len(blockers) * 3, 15)
    return max(0.0, min(100.0, float(base)))


async def generate_accountability_snapshot(
    db: AsyncSession,
    user_id: UUID,
    period_start: date,
    period_end: date,
) -> AccountabilitySnapshot:
    goals_summary = await _goal_summary(db, user_id)
    tasks_summary = await _task_summary(db, user_id, period_start, period_end)
    habits_summary = await _habit_summary(db, user_id, period_start, period_end)
    blockers = await _blockers(db, user_id, period_start, period_end)
    score = _snapshot_score(tasks_summary, habits_summary, goals_summary, blockers)
    goals = goals_summary.get("goals") or []
    reflection = None
    if goals:
        first_goal = goals[0]
        reflection = (
            f"You are still moving toward {first_goal['title']}."
            if tasks_summary.get("done")
            else f"You said you wanted to make progress on {first_goal['title']}."
        )
        if blockers:
            reflection += f" The main blockers were: {', '.join(blockers[:3])}."
    snapshot = AccountabilitySnapshot(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        goals_summary=goals_summary,
        tasks_summary=tasks_summary,
        habits_summary=habits_summary,
        blockers=blockers,
        score=round(score, 2),
        reflection=reflection,
    )
    db.add(snapshot)
    await db.commit()
    await db.refresh(snapshot)
    return snapshot


async def summarize_goal_progress(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    goals = await list_active_goals(db, user_id)
    return {
        "goals": [
            {
                "id": str(goal.id),
                "title": goal.title,
                "life_area": goal.life_area,
                "status": goal.status,
            }
            for goal in goals
        ]
    }


async def compare_periods(
    db: AsyncSession,
    user_id: UUID,
    previous_period: tuple[date, date],
    current_period: tuple[date, date],
) -> dict[str, object]:
    prev_snapshot = await _period_compare(db, user_id, previous_period)
    current_snapshot = await _period_compare(db, user_id, current_period)
    blockers = current_snapshot["blockers"] or []
    slowdown = current_snapshot["tasks_done"] <= prev_snapshot["tasks_done"]
    question = "What got in the way?"
    if blockers:
        question = (
            "That slowed down a bit. What got in the way - "
            + ", ".join(blockers[:3])
            + "?"
        )
    return {
        "previous": prev_snapshot,
        "current": current_snapshot,
        "change": {
            "tasks_done": current_snapshot["tasks_done"] - prev_snapshot["tasks_done"],
            "logs": current_snapshot["habit_logs"] - prev_snapshot["habit_logs"],
            "slowdown": slowdown,
        },
        "accountability_question": question,
    }


async def _period_compare(db: AsyncSession, user_id: UUID, period: tuple[date, date]) -> dict[str, object]:
    start, end = period
    tasks = await _task_summary(db, user_id, start, end)
    habits = await _habit_summary(db, user_id, start, end)
    blockers = await _blockers(db, user_id, start, end)
    return {
        "period_start": start,
        "period_end": end,
        "tasks_done": int(tasks.get("done", 0) or 0),
        "tasks_open": int(tasks.get("open", 0) or 0),
        "habit_logs": int(habits.get("logs", 0) or 0),
        "blockers": blockers,
    }


async def generate_accountability_prompt(db: AsyncSession, user_id: UUID) -> str:
    end = datetime.now(UTC).date()
    start = end - timedelta(days=6)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    comparison = await compare_periods(db, user_id, (prev_start, prev_end), (start, end))
    return comparison["accountability_question"]


async def latest_accountability_snapshot(db: AsyncSession, user_id: UUID) -> AccountabilitySnapshot | None:
    result = await db.execute(
        select(AccountabilitySnapshot)
        .where(AccountabilitySnapshot.user_id == user_id)
        .order_by(AccountabilitySnapshot.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
