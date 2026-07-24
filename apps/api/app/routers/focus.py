from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.focus_session_service import (
    end_focus_session,
    focus_session_to_dict,
    pause_focus_session,
    resume_focus_session,
    start_focus_session,
)

router = APIRouter(prefix="/focus", tags=["focus"])


@router.post("/today-items/{today_item_id}/start", status_code=201)
async def start_focus(
    today_item_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await start_focus_session(db, user.id, today_item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Today item not found")
    return focus_session_to_dict(row)


@router.post("/sessions/{session_id}/pause")
async def pause_focus(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await pause_focus_session(db, user.id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Focus session not found")
    return focus_session_to_dict(row)


@router.post("/sessions/{session_id}/resume")
async def resume_focus(
    session_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await resume_focus_session(db, user.id, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Focus session not found")
    return focus_session_to_dict(row)


@router.post("/sessions/{session_id}/end")
async def end_focus(
    session_id: UUID,
    body: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await end_focus_session(db, user.id, session_id, notes=(body or {}).get("notes"))
    if row is None:
        raise HTTPException(status_code=404, detail="Focus session not found")
    return focus_session_to_dict(row)
