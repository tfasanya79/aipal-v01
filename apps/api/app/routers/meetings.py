from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services import meeting_assistant_service as meetings

router = APIRouter(prefix="/meetings", tags=["meetings"])


class MeetingBody(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime | None = None
    participants: list[str] | dict | None = None
    location: str | None = None
    meeting_link: str | None = None
    project_id: UUID | None = None
    notes: str | None = None
    status: str | None = None


class MeetingPatch(BaseModel):
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    participants: list[str] | dict | None = None
    location: str | None = None
    meeting_link: str | None = None
    project_id: UUID | None = None
    notes: str | None = None
    status: str | None = None


class NotesBody(BaseModel):
    content: str


@router.get("")
async def list_meetings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [meetings.meeting_to_dict(row) for row in await meetings.list_meetings(db, user.id)]


@router.get("/upcoming")
async def upcoming_meetings(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [meetings.meeting_to_dict(row) for row in await meetings.list_upcoming_meetings(db, user.id)]


@router.post("", status_code=201)
async def create_meeting(
    body: MeetingBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await meetings.create_meeting(db, user.id, body.model_dump())
    return meetings.meeting_to_dict(row)


@router.get("/{meeting_id}")
async def get_meeting(
    meeting_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await meetings.get_meeting(db, user.id, meeting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meetings.meeting_to_dict(row)


@router.patch("/{meeting_id}")
async def patch_meeting(
    meeting_id: UUID,
    body: MeetingPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await meetings.update_meeting(db, user.id, meeting_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meetings.meeting_to_dict(row)


@router.post("/{meeting_id}/brief")
async def meeting_brief(
    meeting_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await meetings.prepare_meeting_brief(db, user, meeting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return result


@router.post("/{meeting_id}/notes")
async def meeting_notes(
    meeting_id: UUID,
    body: NotesBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await meetings.create_meeting_notes(db, user.id, meeting_id, body.content)
    if row is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meetings.note_to_dict(row)


@router.post("/{meeting_id}/summarize")
async def meeting_summary(
    meeting_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await meetings.summarize_meeting(db, user.id, meeting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    return result


@router.post("/{meeting_id}/followups")
async def meeting_followups(
    meeting_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await meetings.create_followups_from_meeting(db, user.id, meeting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Meeting notes not found")
    return {"followups": result}
