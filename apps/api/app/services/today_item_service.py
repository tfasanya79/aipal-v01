from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Commitment, Notification, NotificationPreference, Reminder, Task, TodayItem


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _priority_text(value: int | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return {0: "low", 1: "medium", 2: "high", 3: "urgent"}.get(value, "medium")


def _event_time(item: TodayItem) -> datetime | None:
    return item.start_time or item.due_at


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time())
    return start, start + timedelta(days=1)


def _item_on_day_clause(day: date):
    start, end = _day_bounds(day)
    return or_(
        and_(TodayItem.start_time.is_not(None), TodayItem.start_time >= start, TodayItem.start_time < end),
        and_(TodayItem.start_time.is_(None), TodayItem.due_at.is_not(None), TodayItem.due_at >= start, TodayItem.due_at < end),
        and_(TodayItem.start_time.is_(None), TodayItem.due_at.is_(None), TodayItem.created_at >= start, TodayItem.created_at < end),
    )


def today_item_to_dict(item: TodayItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "user_id": str(item.user_id),
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "due_at": item.due_at,
        "status": item.status,
        "priority": item.priority,
        "source": item.source,
        "goal_id": str(item.goal_id) if item.goal_id else None,
        "task_id": item.task_id,
        "calendar_event_id": str(item.calendar_event_id) if item.calendar_event_id else None,
        "reminder_id": str(item.reminder_id) if item.reminder_id else None,
        "habit_id": str(item.habit_id) if item.habit_id else None,
        "reflection_id": str(item.reflection_id) if item.reflection_id else None,
        "commitment_id": str(item.commitment_id) if item.commitment_id else None,
        "metadata": item.metadata_json,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def _agenda_section(item: TodayItem) -> str:
    if item.status == "completed":
        return "completed"
    if item.status in {"cancelled", "dismissed"}:
        return "dismissed"
    if item.type in {"meeting", "calendar"}:
        return "meetings"
    if item.type == "focus":
        return "focus"
    when = _event_time(item)
    if when is None:
        return "unscheduled"
    hour = when.hour
    if hour < 12:
        return "morning"
    if hour >= 17:
        return "evening"
    return "work"


def group_agenda_items(items: list[TodayItem]) -> dict[str, list[dict[str, Any]]]:
    grouped = {
        "morning": [],
        "work": [],
        "meetings": [],
        "focus": [],
        "evening": [],
        "unscheduled": [],
        "completed": [],
        "dismissed": [],
    }
    for item in items:
        grouped[_agenda_section(item)].append(today_item_to_dict(item))
    return grouped


async def list_agenda(db: AsyncSession, user_id: uuid.UUID, day: date | None = None) -> dict[str, Any]:
    target = day or date.today()
    items = await list_today_items(db, user_id, target)
    grouped = group_agenda_items(items)
    open_count = sum(
        1
        for item in items
        if item.status not in {"completed", "cancelled", "dismissed"}
    )
    return {
        "date": target.isoformat(),
        "sections": grouped,
        "items": [today_item_to_dict(item) for item in items],
        "summary": {
            "total": len(items),
            "open": open_count,
            "completed": len(grouped["completed"]),
        },
    }


def notification_to_dict(row: Notification) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "today_item_id": str(row.today_item_id) if row.today_item_id else None,
        "title": row.title,
        "body": row.body,
        "type": row.type,
        "channel": row.channel,
        "scheduled_for": row.scheduled_for,
        "sent_at": row.sent_at,
        "read_at": row.read_at,
        "status": row.status,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def preference_to_dict(row: NotificationPreference) -> dict[str, Any]:
    return {
        "in_app_enabled": row.in_app_enabled,
        "email_enabled": row.email_enabled,
        "push_enabled": row.push_enabled,
        "reminder_lead_minutes": row.reminder_lead_minutes,
        "meeting_lead_minutes": row.meeting_lead_minutes,
        "quiet_hours_start": row.quiet_hours_start,
        "quiet_hours_end": row.quiet_hours_end,
    }


async def get_or_create_preferences(db: AsyncSession, user_id: uuid.UUID) -> NotificationPreference:
    result = await db.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = NotificationPreference(user_id=user_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_preferences(db: AsyncSession, user_id: uuid.UUID, data: dict[str, Any]) -> NotificationPreference:
    row = await get_or_create_preferences(db, user_id)
    for key in (
        "in_app_enabled",
        "email_enabled",
        "push_enabled",
        "reminder_lead_minutes",
        "meeting_lead_minutes",
        "quiet_hours_start",
        "quiet_hours_end",
    ):
        if key in data and data[key] is not None:
            setattr(row, key, data[key])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def ensure_no_duplicate_today_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID | int | None,
) -> TodayItem | None:
    if source_id is None:
        return None
    column = {
        "task": TodayItem.task_id,
        "reminder": TodayItem.reminder_id,
        "commitment": TodayItem.commitment_id,
        "habit": TodayItem.habit_id,
        "reflection": TodayItem.reflection_id,
        "calendar": TodayItem.calendar_event_id,
        "meeting": TodayItem.calendar_event_id,
    }.get(source_type)
    if column is None:
        return None
    result = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id, column == source_id))
    return result.scalar_one_or_none()


async def create_today_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    type: str,
    title: str,
    description: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    due_at: datetime | None = None,
    status: str = "open",
    priority: str | None = None,
    source: str | None = "manual",
    goal_id: uuid.UUID | None = None,
    task_id: int | None = None,
    calendar_event_id: uuid.UUID | None = None,
    reminder_id: uuid.UUID | None = None,
    habit_id: uuid.UUID | None = None,
    reflection_id: uuid.UUID | None = None,
    commitment_id: uuid.UUID | None = None,
    metadata: dict | list | None = None,
    created_by: str = "aipal",
    create_notifications: bool = True,
) -> TodayItem:
    for source_type, source_id in (
        ("task", task_id),
        ("reminder", reminder_id),
        ("commitment", commitment_id),
        ("habit", habit_id),
        ("reflection", reflection_id),
        ("calendar", calendar_event_id),
    ):
        duplicate = await ensure_no_duplicate_today_item(db, user_id, source_type, source_id)
        if duplicate is not None:
            return duplicate

    row = TodayItem(
        user_id=user_id,
        type=type,
        title=title.strip(),
        description=description,
        start_time=start_time,
        end_time=end_time,
        due_at=due_at,
        status=status,
        priority=priority,
        source=source,
        goal_id=goal_id,
        task_id=task_id,
        calendar_event_id=calendar_event_id,
        reminder_id=reminder_id,
        habit_id=habit_id,
        reflection_id=reflection_id,
        commitment_id=commitment_id,
        metadata_json=metadata,
        created_by=created_by,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    if create_notifications:
        await create_notifications_for_today_item(db, user_id, row)
    return row


async def create_from_task(db: AsyncSession, user_id: uuid.UUID, task: Task) -> TodayItem:
    status = "completed" if task.status == "done" else "open"
    existing = await ensure_no_duplicate_today_item(db, user_id, "task", task.id)
    if existing is not None:
        existing.title = task.title
        existing.description = task.notes
        existing.due_at = task.due_at
        existing.priority = _priority_text(task.priority)
        existing.status = status
        existing.goal_id = task.goal_id
        existing.updated_at = _utcnow()
        await _cancel_pending_notifications(db, user_id, existing.id)
        await db.commit()
        await db.refresh(existing)
        from .memory_manager import memory_manager
        await memory_manager.index_row(db, existing)
        await create_notifications_for_today_item(db, user_id, existing)
        return existing
    return await create_today_item(
        db,
        user_id,
        type="task",
        title=task.title,
        description=task.notes,
        due_at=task.due_at,
        status=status,
        priority=_priority_text(task.priority),
        source=task.source or "task",
        goal_id=task.goal_id,
        task_id=task.id,
        created_by="user" if task.source == "manual" else "aipal",
    )


async def create_from_reminder(db: AsyncSession, user_id: uuid.UUID, reminder: Reminder) -> TodayItem:
    existing = await ensure_no_duplicate_today_item(db, user_id, "reminder", reminder.id)
    if existing is not None:
        existing.title = reminder.title
        existing.start_time = reminder.remind_at
        existing.due_at = reminder.remind_at
        existing.status = "scheduled" if reminder.status == "scheduled" else reminder.status
        existing.task_id = reminder.task_id
        existing.updated_at = _utcnow()
        await _cancel_pending_notifications(db, user_id, existing.id)
        await db.commit()
        await db.refresh(existing)
        from .memory_manager import memory_manager
        await memory_manager.index_row(db, existing)
        await create_notifications_for_today_item(db, user_id, existing)
        return existing
    return await create_today_item(
        db,
        user_id,
        type="reminder",
        title=reminder.title,
        start_time=reminder.remind_at,
        due_at=reminder.remind_at,
        status="scheduled" if reminder.status == "scheduled" else reminder.status,
        priority="medium",
        source="reminder",
        task_id=reminder.task_id,
        reminder_id=reminder.id,
        metadata={"recurrence_rule": reminder.recurrence_rule},
    )


async def create_from_commitment(db: AsyncSession, user_id: uuid.UUID, commitment: Commitment) -> TodayItem:
    when = commitment.follow_up_at or commitment.due_at
    existing = await ensure_no_duplicate_today_item(db, user_id, "commitment", commitment.id)
    if existing is not None:
        existing.title = commitment.title
        existing.description = commitment.content
        existing.due_at = when
        existing.status = "completed" if commitment.status == "completed" else ("dismissed" if commitment.status == "dismissed" else "open")
        existing.metadata_json = {"confidence": float(commitment.confidence or 0.0), "related_entity_name": commitment.related_entity_name}
        existing.updated_at = _utcnow()
        await _cancel_pending_notifications(db, user_id, existing.id)
        await db.commit()
        await db.refresh(existing)
        await create_notifications_for_today_item(db, user_id, existing)
        return existing
    return await create_today_item(
        db,
        user_id,
        type="commitment",
        title=commitment.title,
        description=commitment.content,
        due_at=when,
        status="completed" if commitment.status == "completed" else ("dismissed" if commitment.status == "dismissed" else "open"),
        priority="medium",
        source="commitment",
        commitment_id=commitment.id,
        metadata={"confidence": float(commitment.confidence or 0.0), "related_entity_name": commitment.related_entity_name},
    )


async def create_from_meeting(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    title: str,
    start_time: datetime,
    end_time: datetime | None = None,
    description: str | None = None,
    calendar_event_id: uuid.UUID | None = None,
    source: str = "conversation",
) -> TodayItem:
    return await create_today_item(
        db,
        user_id,
        type="meeting",
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        due_at=start_time,
        status="scheduled",
        priority="medium",
        source=source,
        calendar_event_id=calendar_event_id or uuid.uuid4(),
    )


async def create_from_plan(db: AsyncSession, user_id: uuid.UUID, plan_items: list[dict[str, Any]]) -> list[TodayItem]:
    created: list[TodayItem] = []
    for idx, item in enumerate(plan_items[:12]):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        due_at = item.get("due_at")
        if isinstance(due_at, str):
            try:
                due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
            except ValueError:
                due_at = None
        row = await create_today_item(
            db,
            user_id,
            type=str(item.get("type") or "suggested_plan"),
            title=title,
            description=item.get("notes") or item.get("description"),
            start_time=due_at,
            due_at=due_at,
            priority=_priority_text(item.get("priority")),
            source="ai_plan",
            metadata={"sort_order": idx, "category": item.get("category")},
        )
        created.append(row)
    return created


async def list_today_items(db: AsyncSession, user_id: uuid.UUID, day: date | None = None) -> list[TodayItem]:
    q = select(TodayItem).where(TodayItem.user_id == user_id)
    if day is not None:
        q = q.where(_item_on_day_clause(day))
    q = q.order_by(TodayItem.start_time.asc().nulls_last(), TodayItem.due_at.asc().nulls_last(), TodayItem.created_at.asc())
    result = await db.execute(q)
    return list(result.scalars().all())


async def list_range(db: AsyncSession, user_id: uuid.UUID, start_date: date, end_date: date) -> list[TodayItem]:
    start, _ = _day_bounds(start_date)
    _, end = _day_bounds(end_date)
    result = await db.execute(
        select(TodayItem)
        .where(
            TodayItem.user_id == user_id,
            or_(
                and_(TodayItem.start_time.is_not(None), TodayItem.start_time >= start, TodayItem.start_time < end),
                and_(TodayItem.start_time.is_(None), TodayItem.due_at.is_not(None), TodayItem.due_at >= start, TodayItem.due_at < end),
            ),
        )
        .order_by(TodayItem.start_time.asc().nulls_last(), TodayItem.due_at.asc().nulls_last())
    )
    return list(result.scalars().all())


async def get_today_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> TodayItem | None:
    result = await db.execute(select(TodayItem).where(TodayItem.user_id == user_id, TodayItem.id == item_id))
    return result.scalar_one_or_none()


async def update_today_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any]) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    for key, column in (
        ("type", "type"),
        ("title", "title"),
        ("description", "description"),
        ("start_time", "start_time"),
        ("end_time", "end_time"),
        ("due_at", "due_at"),
        ("status", "status"),
        ("priority", "priority"),
        ("metadata", "metadata_json"),
    ):
        if key in data and data[key] is not None:
            setattr(row, column, data[key])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    await create_notifications_for_today_item(db, user_id, row)
    return row


async def complete_today_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    row.status = "completed"
    row.updated_at = _utcnow()
    if row.task_id is not None:
        task = await db.get(Task, row.task_id)
        if task is not None and task.user_id == user_id:
            task.status = "done"
            task.completed_at = _utcnow()
    if row.reminder_id is not None:
        reminder = await db.get(Reminder, row.reminder_id)
        if reminder is not None and reminder.user_id == user_id:
            reminder.status = "done"
    if row.commitment_id is not None:
        commitment = await db.get(Commitment, row.commitment_id)
        if commitment is not None and commitment.user_id == user_id:
            commitment.status = "completed"
    await _cancel_pending_notifications(db, user_id, row.id)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def cancel_today_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    row.status = "cancelled"
    row.updated_at = _utcnow()
    if row.reminder_id is not None:
        reminder = await db.get(Reminder, row.reminder_id)
        if reminder is not None and reminder.user_id == user_id:
            reminder.status = "cancelled"
    if row.commitment_id is not None:
        commitment = await db.get(Commitment, row.commitment_id)
        if commitment is not None and commitment.user_id == user_id:
            commitment.status = "dismissed"
    await _cancel_pending_notifications(db, user_id, row.id)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def reschedule_today_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    new_time: datetime,
) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    row.start_time = new_time if row.type in {"meeting", "reminder", "calendar"} else row.start_time
    row.due_at = new_time
    row.status = "scheduled" if row.type in {"meeting", "reminder", "calendar"} else "open"
    row.updated_at = _utcnow()
    if row.task_id is not None:
        task = await db.get(Task, row.task_id)
        if task is not None and task.user_id == user_id:
            task.due_at = new_time
    if row.reminder_id is not None:
        reminder = await db.get(Reminder, row.reminder_id)
        if reminder is not None and reminder.user_id == user_id:
            reminder.remind_at = new_time
            reminder.status = "scheduled"
    await _cancel_pending_notifications(db, user_id, row.id)
    await db.commit()
    await db.refresh(row)
    await create_notifications_for_today_item(db, user_id, row)
    return row


async def snooze_today_item(
    db: AsyncSession,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    minutes: int = 30,
) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    base = row.due_at or row.start_time or _utcnow()
    return await reschedule_today_item(db, user_id, item_id, base + timedelta(minutes=max(minutes, 1)))


async def start_focus_from_today_item(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> TodayItem | None:
    row = await get_today_item(db, user_id, item_id)
    if row is None:
        return None
    metadata = dict(row.metadata_json or {})
    metadata["focus_started_at"] = _utcnow().isoformat()
    row.metadata_json = metadata
    row.status = "scheduled" if row.status == "open" else row.status
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def sync_from_existing_models(db: AsyncSession, user_id: uuid.UUID) -> list[TodayItem]:
    created: list[TodayItem] = []
    for model, creator in (
        (Task, create_from_task),
        (Reminder, create_from_reminder),
        (Commitment, create_from_commitment),
    ):
        result = await db.execute(select(model).where(model.user_id == user_id))
        for row in result.scalars().all():
            created.append(await creator(db, user_id, row))
    return created


async def _cancel_pending_notifications(db: AsyncSession, user_id: uuid.UUID, today_item_id: uuid.UUID) -> None:
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.today_item_id == today_item_id,
            Notification.status == "pending",
        )
    )
    for row in result.scalars().all():
        row.status = "cancelled"
        row.updated_at = _utcnow()


def _notification_type(item: TodayItem) -> str:
    return {
        "reminder": "reminder",
        "meeting": "meeting",
        "calendar": "meeting",
        "task": "task_due",
        "commitment": "commitment_followup",
    }.get(item.type, "plan_item")


def _lead_minutes(item: TodayItem, prefs: NotificationPreference) -> int:
    if item.type in {"meeting", "calendar"}:
        return prefs.meeting_lead_minutes
    if item.type in {"reminder", "task", "commitment"}:
        return prefs.reminder_lead_minutes
    return 0


def _notification_body(item: TodayItem) -> str:
    label = item.title.strip()
    if item.type == "meeting":
        return f"Meeting coming up: {label}."
    if item.type == "commitment":
        return f"Gentle follow-up: {label}."
    return f"AiPal reminder: {label}."


async def _notification_exists(
    db: AsyncSession,
    user_id: uuid.UUID,
    today_item_id: uuid.UUID,
    *,
    channel: str,
    type: str,
) -> bool:
    result = await db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.today_item_id == today_item_id,
            Notification.channel == channel,
            Notification.type == type,
            Notification.status != "cancelled",
        )
    )
    return result.first() is not None


async def create_notifications_for_today_item(db: AsyncSession, user_id: uuid.UUID, item: TodayItem) -> list[Notification]:
    scheduled_for = _event_time(item)
    if scheduled_for is None or item.status in {"completed", "cancelled", "dismissed"}:
        return []
    prefs = await get_or_create_preferences(db, user_id)
    ntype = _notification_type(item)
    lead = _lead_minutes(item, prefs)
    notify_at = scheduled_for - timedelta(minutes=lead)
    rows: list[Notification] = []
    for channel, enabled in (("in_app", prefs.in_app_enabled), ("push", prefs.push_enabled), ("email", prefs.email_enabled)):
        if not enabled:
            continue
        if await _notification_exists(db, user_id, item.id, channel=channel, type=ntype):
            continue
        row = Notification(
            user_id=user_id,
            today_item_id=item.id,
            title=item.title,
            body=_notification_body(item),
            type=ntype,
            channel=channel,
            scheduled_for=notify_at,
            status="pending",
            metadata_json={"event_time": scheduled_for.isoformat(), "today_item_type": item.type},
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    return rows


async def list_notifications(db: AsyncSession, user_id: uuid.UUID) -> list[Notification]:
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.scheduled_for.asc().nulls_last(), Notification.created_at.desc())
    )
    return list(result.scalars().all())


async def mark_notification_read(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
    result = await db.execute(select(Notification).where(Notification.user_id == user_id, Notification.id == notification_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.read_at = _utcnow()
    row.status = "read"
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def dismiss_notification(db: AsyncSession, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification | None:
    result = await db.execute(select(Notification).where(Notification.user_id == user_id, Notification.id == notification_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = "cancelled"
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


def _parse_time_hint(text: str) -> tuple[int, int]:
    lower = text.lower()
    match = re.search(r"\b(?:at|by)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", lower)
    if not match:
        return 9, 0
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    ampm = match.group(3)
    if ampm == "pm" and hour < 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if ampm is None and hour < 8:
        hour += 12
    return hour, minute


def _has_explicit_time(text: str) -> bool:
    return bool(re.search(r"\b(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b|\b\d{1,2}(?::\d{2})\s*(?:am|pm)\b", text, re.IGNORECASE))


def _has_date_hint(text: str) -> bool:
    lower = text.lower()
    if any(word in lower for word in ("today", "tomorrow", "next week", "next month")):
        return True
    if re.search(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", lower):
        return True
    if re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b", lower):
        return True
    return False


def parse_action_datetime(text: str, *, now: datetime | None = None) -> datetime | None:
    now = now or _utcnow()
    lower = text.lower()
    hour, minute = _parse_time_hint(text)
    if "tomorrow" in lower:
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "next week" in lower:
        return (now + timedelta(days=7)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    iso_date = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", lower)
    if iso_date:
        return datetime(
            int(iso_date.group(1)),
            int(iso_date.group(2)),
            int(iso_date.group(3)),
            hour,
            minute,
            tzinfo=UTC,
        )
    slash_date = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", lower)
    if slash_date:
        month = int(slash_date.group(1))
        day = int(slash_date.group(2))
        year = int(slash_date.group(3) or now.year)
        if year < 100:
            year += 2000
        candidate = datetime.combine(date(year, month, day), time(hour, minute), tzinfo=UTC)
        if candidate < now:
            candidate = candidate.replace(year=year + 1)
        return candidate
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    for name, index in weekdays.items():
        if name in lower:
            days = (index - now.weekday()) % 7
            if days == 0:
                days = 7
            return (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "today" in lower or re.search(r"\b(at|by)\s+\d", lower):
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return None


def extract_reminder_request(text: str) -> tuple[str, datetime] | None:
    match = re.search(r"^\s*remind\s+me\s+to\s+(.+)", text, re.IGNORECASE)
    if not match:
        return None
    when = parse_action_datetime(text)
    if when is None:
        return None
    title = re.sub(r"\b(?:tomorrow|today|next week|on\s+\w+day|at\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\b", "", match.group(1), flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" .")
    return (title[:1].upper() + title[1:])[:255], when


def extract_meeting_request(text: str) -> tuple[str, datetime] | None:
    if not re.search(r"\b(schedule|book|set up)\b.*\b(meeting|call)\b", text, re.IGNORECASE):
        return None
    when = parse_action_datetime(text)
    if when is None:
        return None
    with_match = re.search(r"\bwith\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", text)
    person = with_match.group(1) if with_match else "someone"
    return f"Meeting with {person}", when


def ambiguous_agenda_request(text: str) -> str | None:
    lower = text.lower().strip()
    if lower.startswith("remind me") and not (_has_date_hint(text) and _has_explicit_time(text)):
        return "What day and time should I remind you?"
    if re.search(r"^\s*(schedule|book|set up)\b.*\b(meeting|call)\b", text, re.IGNORECASE) and not (
        _has_date_hint(text) and _has_explicit_time(text)
    ):
        return "What day and time should I schedule it for?"
    return None
