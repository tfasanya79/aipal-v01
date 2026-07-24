from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Notification, User
from ..services.email_notification_service import send_email_notification


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def dispatch_due_notifications(db: AsyncSession, *, limit: int = 100) -> dict[str, int]:
    now = _utcnow()
    result = await db.execute(
        select(Notification)
        .where(
            Notification.status == "pending",
            Notification.scheduled_for.is_not(None),
            Notification.scheduled_for <= now,
        )
        .order_by(Notification.scheduled_for.asc())
        .limit(limit)
    )
    sent = 0
    failed = 0
    for notification in result.scalars().all():
        if notification.channel == "email":
            user = await db.get(User, notification.user_id)
            if user is None:
                notification.status = "failed"
                failed += 1
                continue
            before = notification.status
            await send_email_notification(db, user, notification)
            sent += 1 if notification.status == "sent" else 0
            failed += 1 if before != notification.status and notification.status == "failed" else 0
            continue
        notification.status = "sent"
        notification.sent_at = now
        notification.updated_at = now
        sent += 1
    await db.commit()
    return {"sent": sent, "failed": failed}
