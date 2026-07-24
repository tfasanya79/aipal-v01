from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Commitment, Meeting, Notification, TodayItem, User
from .brain_briefing_service import generate_notification_briefing
from .today_item_service import get_or_create_preferences, notification_to_dict


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


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


async def _exists(db: AsyncSession, user_id: uuid.UUID, notification_type: str, key: str) -> bool:
    result = await db.execute(
        select(Notification.id).where(
            Notification.user_id == user_id,
            Notification.type == notification_type,
            Notification.status != "cancelled",
        )
    )
    for row in result.scalars().all():
        # SQLite JSON querying is inconsistent across test/prod, so inspect in Python.
        notification = await db.get(Notification, row)
        if notification and (notification.metadata_json or {}).get("smart_key") == key:
            return True
    return False


async def _create_rows(
    db: AsyncSession,
    user: User,
    *,
    title: str,
    body: str,
    notification_type: str,
    smart_key: str,
    today_item_id: uuid.UUID | None = None,
    scheduled_for: datetime | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Notification]:
    prefs = await get_or_create_preferences(db, user.id)
    if _quiet_hours_active(prefs.quiet_hours_start, prefs.quiet_hours_end, _utcnow()):
        return []
    rows: list[Notification] = []
    for channel, enabled in (("in_app", prefs.in_app_enabled), ("email", prefs.email_enabled)):
        if not enabled:
            continue
        channel_key = f"{smart_key}:{channel}"
        if await _exists(db, user.id, notification_type, channel_key):
            continue
        row = Notification(
            user_id=user.id,
            today_item_id=today_item_id,
            title=title,
            body=body,
            type=notification_type,
            channel=channel,
            scheduled_for=scheduled_for or _utcnow(),
            status="pending",
            metadata_json={"smart": True, "smart_key": channel_key, **(metadata or {})},
        )
        db.add(row)
        rows.append(row)
    if rows:
        await db.commit()
        for row in rows:
            await db.refresh(row)
    return rows


async def create_smart_meeting_prep_notification(db: AsyncSession, user: User, meeting_id: uuid.UUID) -> list[Notification]:
    meeting = await db.get(Meeting, meeting_id)
    if meeting is None or meeting.user_id != user.id:
        return []
    context = (
        f"Meeting: {meeting.title}\n"
        f"Starts: {meeting.start_time.isoformat()}\n"
        f"Participants: {meeting.participants or []}\n"
        f"Notes: {(meeting.notes or '')[:800]}"
    )
    brief = await generate_notification_briefing(
        db,
        user,
        user_message="Create one smart meeting-prep notification. Keep it short and helpful.",
        trigger_context=context,
    )
    body = str(brief.get("message") or f"You have a meeting coming up: {meeting.title}.")
    notify_at = _aware(meeting.start_time) - timedelta(minutes=30)
    return await _create_rows(
        db,
        user,
        title=f"Prepare for {meeting.title}",
        body=body,
        notification_type="smart_meeting_prep",
        smart_key=f"meeting:{meeting.id}",
        scheduled_for=max(_utcnow(), notify_at),
        metadata={"meeting_id": str(meeting.id)},
    )


async def create_commitment_progress_notification(db: AsyncSession, user: User, *, keyword: str | None = None) -> list[Notification]:
    result = await db.execute(
        select(Commitment)
        .where(Commitment.user_id == user.id, Commitment.status.in_(["open", "completed"]))
        .order_by(Commitment.created_at.desc())
        .limit(50)
    )
    rows = list(result.scalars().all())
    if keyword:
        rows = [row for row in rows if keyword.lower() in f"{row.title} {row.content}".lower()]
    if not rows:
        return []
    completed = len([row for row in rows if row.status == "completed"])
    open_count = len([row for row in rows if row.status == "open"])
    context = f"Commitments tracked: {len(rows)}. Completed: {completed}. Remaining: {open_count}. Keyword: {keyword or 'all'}."
    brief = await generate_notification_briefing(
        db,
        user,
        user_message="Create one gentle commitment-progress notification. Do not shame the user.",
        trigger_context=context,
    )
    body = str(brief.get("message") or f"You have completed {completed}. {open_count} remain if you still want to follow through.")
    key = f"commitment_progress:{keyword or 'all'}:{completed}:{open_count}"
    return await _create_rows(
        db,
        user,
        title="Commitment progress",
        body=body,
        notification_type="smart_commitment_progress",
        smart_key=key,
        metadata={"completed": completed, "remaining": open_count, "keyword": keyword},
    )


async def create_missed_item_followup(db: AsyncSession, user: User, item_id: uuid.UUID) -> list[Notification]:
    item = await db.get(TodayItem, item_id)
    if item is None or item.user_id != user.id or item.status not in {"missed", "open", "scheduled"}:
        return []
    context = f"Today item: {item.title}. Type: {item.type}. Status: {item.status}. Due: {item.due_at or item.start_time}."
    brief = await generate_notification_briefing(
        db,
        user,
        user_message="Create a gentle missed-item follow-up notification. Do not shame the user.",
        trigger_context=context,
    )
    body = str(brief.get("message") or f"You planned {item.title}. Want to revisit it?")
    return await _create_rows(
        db,
        user,
        title="Gentle follow-up",
        body=body,
        notification_type="smart_missed_followup",
        smart_key=f"missed:{item.id}:{item.status}",
        today_item_id=item.id,
        metadata={"today_item_type": item.type, "status": item.status},
    )


async def dispatch_smart_notifications(db: AsyncSession, user: User) -> dict[str, Any]:
    created: list[Notification] = []
    now = _utcnow()
    meeting_result = await db.execute(
        select(Meeting)
        .where(Meeting.user_id == user.id, Meeting.status == "scheduled", Meeting.start_time >= now, Meeting.start_time <= now + timedelta(hours=2))
        .order_by(Meeting.start_time.asc())
        .limit(1)
    )
    meeting = meeting_result.scalar_one_or_none()
    if meeting:
        created.extend(await create_smart_meeting_prep_notification(db, user, meeting.id))

    created.extend(await create_commitment_progress_notification(db, user))
    return {"status": "ok", "notifications": [notification_to_dict(row) for row in created]}
