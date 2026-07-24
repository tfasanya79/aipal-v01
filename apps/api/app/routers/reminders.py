from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import ReminderCreate, ReminderResponse, ReminderUpdate
from ..services.reminder_service import (
    create_reminder,
    delete_reminder,
    list_reminders,
    reminder_to_dict,
    update_reminder,
)
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["reminders"], dependencies=[Depends(rate_limit_dependency("reminders", limit=60))])


@router.get("/reminders", response_model=list[ReminderResponse])
async def get_reminders(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [ReminderResponse(**reminder_to_dict(reminder)) for reminder in await list_reminders(db, user.id)]


@router.post("/reminders", response_model=ReminderResponse)
async def post_reminder(
    body: ReminderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        reminder = await create_reminder(db, user.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ReminderResponse(**reminder_to_dict(reminder))


@router.patch("/reminders/{reminder_id}", response_model=ReminderResponse)
async def patch_reminder(
    reminder_id: UUID,
    body: ReminderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        reminder = await update_reminder(db, user.id, reminder_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return ReminderResponse(**reminder_to_dict(reminder))


@router.delete("/reminders/{reminder_id}")
async def remove_reminder(
    reminder_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_reminder(db, user.id, reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"ok": True}
