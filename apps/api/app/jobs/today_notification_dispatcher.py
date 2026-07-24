from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from ..services.next_item_helper_service import dispatch_next_item_helper
from ..services.today_summary_service import dispatch_today_summary


async def dispatch_morning_today_summaries(db: AsyncSession, *, target_date: date | None = None) -> dict[str, int]:
    result = await db.execute(select(User))
    sent = 0
    for user in result.scalars().all():
        payload = await dispatch_today_summary(db, user, target_date)
        sent += len(payload.get("notifications") or [])
    return {"notifications_created": sent}


async def dispatch_next_item_helpers(db: AsyncSession, *, now: datetime | None = None) -> dict[str, int]:
    result = await db.execute(select(User))
    sent = 0
    for user in result.scalars().all():
        payload = await dispatch_next_item_helper(db, user, now=now)
        sent += len(payload.get("notifications") or [])
    return {"notifications_created": sent}
