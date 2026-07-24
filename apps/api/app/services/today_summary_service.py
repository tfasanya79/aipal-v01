from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification, TodayItem, User
from .today_item_service import get_or_create_preferences, list_today_items, notification_to_dict


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _item_time(item: TodayItem) -> datetime | None:
    return item.start_time or item.due_at


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "Unscheduled"
    hour = value.hour
    minute = value.minute
    suffix = "AM" if hour < 12 else "PM"
    hour = hour % 12 or 12
    return f"{hour}:{minute:02d} {suffix}"


def _summary_metadata(day: date) -> dict[str, Any]:
    return {"kind": "today_summary", "date": day.isoformat()}


async def get_today_agenda(db: AsyncSession, user_id: uuid.UUID, day: date | None = None) -> dict[str, Any]:
    target = day or _utcnow().date()
    items = await list_today_items(db, user_id, target)
    active = [item for item in items if item.status not in {"completed", "cancelled", "dismissed"}]
    scheduled = sorted([item for item in active if _item_time(item) is not None], key=lambda item: _item_time(item) or datetime.max)
    unscheduled = [item for item in active if _item_time(item) is None]
    return {
        "date": target.isoformat(),
        "items": [
            {
                "id": str(item.id),
                "title": item.title,
                "type": item.type,
                "status": item.status,
                "time": _format_time(_item_time(item)),
                "scheduled_at": _item_time(item),
            }
            for item in [*scheduled, *unscheduled]
        ],
        "scheduled_count": len(scheduled),
        "unscheduled_count": len(unscheduled),
        "total": len(active),
    }


async def generate_today_summary(db: AsyncSession, user: User, day: date | None = None) -> dict[str, Any]:
    agenda = await get_today_agenda(db, user.id, day)
    items = agenda["items"]
    if not items:
        body = "Your AiPal plan for today is clear. Nothing is scheduled yet."
    else:
        lines = [f"{item['time']} — {item['title']}" for item in items[:12]]
        body = f"You have {len(items)} thing{'s' if len(items) != 1 else ''} today:\n" + "\n".join(f"* {line}" for line in lines)
    return {
        "title": "Your AiPal plan for today",
        "body": body,
        "agenda": agenda,
        "status": "ok",
    }


async def _notification_exists(db: AsyncSession, user_id: uuid.UUID, *, channel: str, day: date) -> bool:
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == "today_summary",
            Notification.channel == channel,
            Notification.status != "cancelled",
        )
    )
    expected = _summary_metadata(day)
    return any((row.metadata_json or {}) == expected for row in result.scalars().all())


async def create_today_summary_notification(db: AsyncSession, user: User, day: date | None = None) -> list[Notification]:
    target = day or _utcnow().date()
    prefs = await get_or_create_preferences(db, user.id)
    summary = await generate_today_summary(db, user, target)
    rows: list[Notification] = []
    for channel, enabled in (("in_app", prefs.in_app_enabled), ("email", prefs.email_enabled)):
        if not enabled or await _notification_exists(db, user.id, channel=channel, day=target):
            continue
        row = Notification(
            user_id=user.id,
            today_item_id=None,
            title=str(summary["title"]),
            body=str(summary["body"]),
            type="today_summary",
            channel=channel,
            scheduled_for=_utcnow(),
            status="pending",
            metadata_json=_summary_metadata(target),
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    return rows


async def send_today_summary_email(db: AsyncSession, user: User, day: date | None = None) -> list[dict[str, Any]]:
    rows = await create_today_summary_notification(db, user, day)
    return [notification_to_dict(row) for row in rows if row.channel == "email"]


async def dispatch_today_summary(db: AsyncSession, user: User, day: date | None = None) -> dict[str, Any]:
    summary = await generate_today_summary(db, user, day)
    rows = await create_today_summary_notification(db, user, day)
    return {
        **summary,
        "notifications": [notification_to_dict(row) for row in rows],
    }
