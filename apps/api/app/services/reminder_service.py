from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Reminder, Task
from ..schemas import ReminderCreate, ReminderUpdate


async def _owned_task_or_none(db: AsyncSession, user_id: UUID, task_id: int | None) -> Task | None:
    if task_id is None:
        return None
    result = await db.execute(select(Task).where(Task.id == task_id, Task.user_id == user_id))
    return result.scalar_one_or_none()


async def list_reminders(db: AsyncSession, user_id: UUID) -> list[Reminder]:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user_id).order_by(Reminder.remind_at.asc())
    )
    return list(result.scalars().all())


async def get_reminder(db: AsyncSession, user_id: UUID, reminder_id: UUID) -> Reminder | None:
    result = await db.execute(
        select(Reminder).where(Reminder.user_id == user_id, Reminder.id == reminder_id)
    )
    return result.scalar_one_or_none()


async def create_reminder(db: AsyncSession, user_id: UUID, data: ReminderCreate) -> Reminder:
    if data.task_id is not None:
        task = await _owned_task_or_none(db, user_id, data.task_id)
        if task is None:
            raise ValueError("Task not found")
    reminder = Reminder(
        user_id=user_id,
        task_id=data.task_id,
        title=data.title.strip(),
        remind_at=data.remind_at,
        recurrence_rule=data.recurrence_rule,
        status=data.status,
    )
    db.add(reminder)
    await db.commit()
    await db.refresh(reminder)
    from .today_item_service import create_from_reminder

    await create_from_reminder(db, user_id, reminder)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, reminder)
    return reminder


async def update_reminder(db: AsyncSession, user_id: UUID, reminder_id: UUID, data: ReminderUpdate) -> Reminder | None:
    reminder = await get_reminder(db, user_id, reminder_id)
    if reminder is None:
        return None
    if data.task_id is not None:
        task = await _owned_task_or_none(db, user_id, data.task_id)
        if task is None:
            raise ValueError("Task not found")
    for key in ("title", "remind_at", "recurrence_rule", "status", "task_id"):
        value = getattr(data, key)
        if value is not None:
            setattr(reminder, key, value)
    reminder.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(reminder)
    from .today_item_service import create_from_reminder

    await create_from_reminder(db, user_id, reminder)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, reminder)
    return reminder


async def delete_reminder(db: AsyncSession, user_id: UUID, reminder_id: UUID) -> bool:
    reminder = await get_reminder(db, user_id, reminder_id)
    if reminder is None:
        return False
    from .today_item_service import cancel_today_item, ensure_no_duplicate_today_item

    item = await ensure_no_duplicate_today_item(db, user_id, "reminder", reminder.id)
    if item is not None:
        await cancel_today_item(db, user_id, item.id)
    await db.delete(reminder)
    await db.commit()
    from .memory_manager import memory_manager
    await memory_manager.delete_source(db, user_id, "reminder", str(reminder_id))
    return True


def reminder_to_dict(reminder: Reminder) -> dict:
    return {
        "id": str(reminder.id),
        "user_id": str(reminder.user_id),
        "task_id": reminder.task_id,
        "title": reminder.title,
        "remind_at": reminder.remind_at,
        "recurrence_rule": reminder.recurrence_rule,
        "status": reminder.status,
        "created_at": reminder.created_at,
        "updated_at": reminder.updated_at,
    }
