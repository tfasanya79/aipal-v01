from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import TodayItemCreate, TodayItemResponse, TodayItemUpdate
from ..services.today_item_service import (
    cancel_today_item,
    complete_today_item,
    create_today_item,
    list_agenda,
    list_range,
    list_today_items,
    reschedule_today_item,
    snooze_today_item,
    start_focus_from_today_item,
    today_item_to_dict,
    update_today_item,
)
from ..timezone_util import user_local_today

router = APIRouter(prefix="/today-items", tags=["today-items"])


@router.get("", response_model=list[TodayItemResponse])
async def get_today_items(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = day or user_local_today(user.timezone)
    return [TodayItemResponse(**today_item_to_dict(row)) for row in await list_today_items(db, user.id, target)]


@router.get("/range", response_model=list[TodayItemResponse])
async def get_today_item_range(
    start_date: date,
    end_date: date,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [TodayItemResponse(**today_item_to_dict(row)) for row in await list_range(db, user.id, start_date, end_date)]


@router.get("/agenda")
async def get_today_agenda(
    day: date | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = day or user_local_today(user.timezone)
    return await list_agenda(db, user.id, target)


@router.post("", response_model=TodayItemResponse, status_code=201)
async def post_today_item(
    body: TodayItemCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await create_today_item(db, user.id, **body.model_dump())
    return TodayItemResponse(**today_item_to_dict(row))


@router.patch("/{item_id}", response_model=TodayItemResponse)
async def patch_today_item(
    item_id: UUID,
    body: TodayItemUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await update_today_item(db, user.id, item_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))


@router.post("/{item_id}/complete", response_model=TodayItemResponse)
async def complete_item(
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await complete_today_item(db, user.id, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))


@router.post("/{item_id}/cancel", response_model=TodayItemResponse)
async def cancel_item(
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await cancel_today_item(db, user.id, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))


@router.post("/{item_id}/reschedule", response_model=TodayItemResponse)
async def reschedule_item(
    item_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw_time = payload.get("new_time") or payload.get("due_at") or payload.get("start_time")
    if not raw_time:
        raise HTTPException(status_code=422, detail="new_time is required")
    new_time = raw_time if isinstance(raw_time, datetime) else datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
    row = await reschedule_today_item(db, user.id, item_id, new_time)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))


@router.post("/{item_id}/snooze", response_model=TodayItemResponse)
async def snooze_item(
    item_id: UUID,
    payload: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    minutes = int((payload or {}).get("minutes", 30))
    row = await snooze_today_item(db, user.id, item_id, minutes)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))


@router.post("/{item_id}/start-focus", response_model=TodayItemResponse)
async def start_focus_item(
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await start_focus_from_today_item(db, user.id, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return TodayItemResponse(**today_item_to_dict(row))
