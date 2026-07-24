from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Goal


async def list_active_goals(db: AsyncSession, user_id: UUID, limit: int = 5) -> list[Goal]:
    result = await db.execute(
        select(Goal)
        .where(Goal.user_id == user_id, Goal.status.in_(("active", "paused")))
        .order_by(Goal.priority.desc(), Goal.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create_goal(db: AsyncSession, user_id: UUID, data: dict) -> Goal:
    target_date = data.get("target_date")
    if isinstance(target_date, str) and target_date:
        target_date = date.fromisoformat(target_date)
    goal = Goal(
        user_id=user_id,
        title=(data.get("title") or "").strip(),
        description=(data.get("description") or None),
        life_area=data.get("life_area"),
        status=data.get("status") or "active",
        priority=data.get("priority") or "medium",
        target_date=target_date,
    )
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, goal)
    return goal


async def update_goal(db: AsyncSession, user_id: UUID, goal_id: UUID, data: dict) -> Goal | None:
    result = await db.execute(select(Goal).where(Goal.user_id == user_id, Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        return None
    for key in ("title", "description", "life_area", "status", "priority", "target_date"):
        if key in data and data[key] is not None:
            value = data[key]
            if key == "target_date" and isinstance(value, str):
                value = date.fromisoformat(value)
            setattr(goal, key, value)
    goal.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(goal)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, goal)
    return goal


async def delete_goal(db: AsyncSession, user_id: UUID, goal_id: UUID) -> bool:
    result = await db.execute(select(Goal).where(Goal.user_id == user_id, Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        return False
    await db.delete(goal)
    await db.commit()
    from .memory_manager import memory_manager
    await memory_manager.delete_source(db, user_id, "goal", str(goal_id))
    return True
