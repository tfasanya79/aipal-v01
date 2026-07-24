from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import NotificationPreferenceResponse, NotificationPreferenceUpdate, NotificationResponse
from ..services.today_item_service import (
    dismiss_notification,
    get_or_create_preferences,
    list_notifications,
    mark_notification_read,
    notification_to_dict,
    preference_to_dict,
    update_preferences,
)
from ..services.smart_notification_service import (
    create_commitment_progress_notification,
    create_missed_item_followup,
    create_smart_meeting_prep_notification,
    dispatch_smart_notifications,
)

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationResponse])
async def get_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [NotificationResponse(**notification_to_dict(row)) for row in await list_notifications(db, user.id)]


@router.patch("/notifications/{notification_id}/read", response_model=NotificationResponse)
async def read_notification(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await mark_notification_read(db, user.id, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationResponse(**notification_to_dict(row))


@router.post("/notifications/{notification_id}/dismiss", response_model=NotificationResponse)
async def dismiss_notification_route(
    notification_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await dismiss_notification(db, user.id, notification_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return NotificationResponse(**notification_to_dict(row))


@router.get("/notification-preferences", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return NotificationPreferenceResponse(**preference_to_dict(await get_or_create_preferences(db, user.id)))


@router.patch("/notification-preferences", response_model=NotificationPreferenceResponse)
async def patch_notification_preferences(
    body: NotificationPreferenceUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await update_preferences(db, user.id, body.model_dump(exclude_none=True))
    return NotificationPreferenceResponse(**preference_to_dict(row))


@router.post("/notifications/smart/dispatch")
async def dispatch_smart_notification_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await dispatch_smart_notifications(db, user)


@router.post("/notifications/smart/meeting/{meeting_id}")
async def smart_meeting_notification_route(
    meeting_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await create_smart_meeting_prep_notification(db, user, meeting_id)
    return {"status": "ok", "notifications": [notification_to_dict(row) for row in rows]}


@router.post("/notifications/smart/commitments")
async def smart_commitment_notification_route(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await create_commitment_progress_notification(db, user, keyword=(body or {}).get("keyword"))
    return {"status": "ok", "notifications": [notification_to_dict(row) for row in rows]}


@router.post("/notifications/smart/missed/{today_item_id}")
async def smart_missed_notification_route(
    today_item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await create_missed_item_followup(db, user, today_item_id)
    return {"status": "ok", "notifications": [notification_to_dict(row) for row in rows]}
