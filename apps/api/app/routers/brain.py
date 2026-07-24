from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.brain_briefing_service import (
    generate_connector_briefing,
    generate_goal_briefing,
    generate_notification_briefing,
    generate_task_briefing,
    generate_today_briefing,
)
from ..services.connectors_service import list_connected_items

router = APIRouter(prefix="/brain/briefing", tags=["brain"])


@router.post("/today")
async def today_briefing(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_today_briefing(db, user, user_message=(body or {}).get("message"))


@router.post("/goals")
async def goals_briefing(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_goal_briefing(db, user, user_message=(body or {}).get("message"))


@router.post("/tasks")
async def tasks_briefing(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_task_briefing(db, user, user_message=(body or {}).get("message"))


@router.post("/notifications")
async def notifications_briefing(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = body or {}
    return await generate_notification_briefing(
        db,
        user,
        user_message=payload.get("message"),
        trigger_context=payload.get("context"),
    )


@router.post("/connectors")
async def connectors_briefing(
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = body or {}
    source_type = str(payload.get("source_type") or payload.get("provider") or "connected sources")
    rows = await list_connected_items(db, user.id, provider=payload.get("provider"))
    evidence = [
        f"{row.provider} {row.item_type}: {row.title} - {row.content_summary or ''}".strip()
        for row in rows[:10]
    ]
    return await generate_connector_briefing(
        db,
        user,
        source_type=source_type,
        items=evidence,
        user_message=payload.get("message"),
    )
