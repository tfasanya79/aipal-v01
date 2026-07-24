from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification, TodayItem, User
from .today_item_service import get_or_create_preferences, notification_to_dict


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _event_time(item: TodayItem) -> datetime | None:
    return item.start_time or item.due_at


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "soon"
    hour = value.hour % 12 or 12
    return f"{hour}:{value.minute:02d} {'AM' if value.hour < 12 else 'PM'}"


def _parse_hhmm(value: str | None) -> int | None:
    if not value:
        return None
    try:
        hour, minute = value.split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return None


def _quiet_hours_active(start: str | None, end: str | None, now: datetime) -> bool:
    start_min = _parse_hhmm(start)
    end_min = _parse_hhmm(end)
    if start_min is None or end_min is None:
        return False
    current = now.hour * 60 + now.minute
    if start_min <= end_min:
        return start_min <= current <= end_min
    return current >= start_min or current <= end_min


async def get_next_upcoming_item(db: AsyncSession, user_id: uuid.UUID, now: datetime | None = None) -> TodayItem | None:
    now = now or _utcnow()
    result = await db.execute(
        select(TodayItem)
        .where(
            TodayItem.user_id == user_id,
            TodayItem.status.not_in(["completed", "cancelled", "dismissed"]),
            or_(
                and_(TodayItem.start_time.is_not(None), TodayItem.start_time >= now),
                and_(TodayItem.start_time.is_(None), TodayItem.due_at.is_not(None), TodayItem.due_at >= now),
            ),
        )
        .order_by(TodayItem.start_time.asc().nulls_last(), TodayItem.due_at.asc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _notification_exists(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID, *, channel: str) -> bool:
    result = await db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.today_item_id == item_id,
            Notification.type == "next_item",
            Notification.channel == channel,
            Notification.status != "cancelled",
        )
    )
    return result.first() is not None


async def create_next_item_notification(db: AsyncSession, user: User, item: TodayItem, *, now: datetime | None = None) -> list[Notification]:
    now = now or _utcnow()
    prefs = await get_or_create_preferences(db, user.id)
    if _quiet_hours_active(prefs.quiet_hours_start, prefs.quiet_hours_end, now):
        return []
    when = _event_time(item)
    body = f'Your next item is "{item.title}" at {_format_time(when)}.'
    rows: list[Notification] = []
    for channel, enabled in (("in_app", prefs.in_app_enabled), ("email", prefs.email_enabled)):
        if not enabled or await _notification_exists(db, user.id, item.id, channel=channel):
            continue
        row = Notification(
            user_id=user.id,
            today_item_id=item.id,
            title="Up next",
            body=body,
            type="next_item",
            channel=channel,
            scheduled_for=now,
            status="pending",
            metadata_json={"kind": "next_item", "event_time": when.isoformat() if when else None, "today_item_type": item.type},
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    return rows


async def send_next_item_email(db: AsyncSession, user: User, item: TodayItem) -> list[dict[str, Any]]:
    rows = await create_next_item_notification(db, user, item)
    return [notification_to_dict(row) for row in rows if row.channel == "email"]


async def dispatch_next_item_helper(db: AsyncSession, user: User, now: datetime | None = None) -> dict[str, Any]:
    item = await get_next_upcoming_item(db, user.id, now)
    if item is None:
        return {"status": "empty", "item": None, "notifications": []}
    rows = await create_next_item_notification(db, user, item, now=now)
    return {
        "status": "ok",
        "item": {
            "id": str(item.id),
            "title": item.title,
            "type": item.type,
            "time": _format_time(_event_time(item)),
        },
        "notifications": [notification_to_dict(row) for row in rows],
    }
