from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.next_item_helper_service import dispatch_next_item_helper, get_next_upcoming_item
from ..services.today_item_service import list_agenda
from ..services.today_summary_service import dispatch_today_summary, generate_today_summary
from ..timezone_util import user_local_today

router = APIRouter(prefix="/today", tags=["today"])


@router.get("/summary")
async def today_summary(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_today_summary(db, user, day)


@router.get("/agenda")
async def today_agenda(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = day or user_local_today(user.timezone)
    return await list_agenda(db, user.id, target)


@router.post("/summary/send")
async def send_today_summary(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await dispatch_today_summary(db, user, day)


@router.get("/next")
async def today_next(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    item = await get_next_upcoming_item(db, user.id)
    if item is None:
        return {"status": "empty", "item": None}
    return {
        "status": "ok",
        "item": {
            "id": str(item.id),
            "title": item.title,
            "type": item.type,
            "start_time": item.start_time,
            "due_at": item.due_at,
            "status": item.status,
        },
    }


@router.post("/next/notify")
async def notify_today_next(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await dispatch_next_item_helper(db, user)
