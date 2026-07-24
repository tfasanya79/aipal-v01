from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services import project_room_service as rooms

router = APIRouter(prefix="/project-rooms", tags=["project-rooms"])


class RoomCreate(BaseModel):
    name: str
    description: str | None = None


class RoomPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    goals: dict | list | None = None
    key_people: dict | list | None = None
    risks: dict | list | None = None
    opportunities: dict | list | None = None


class LinkBody(BaseModel):
    linked_type: str
    linked_id: str


@router.get("")
async def list_project_rooms(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [rooms.room_to_dict(row) for row in await rooms.list_rooms(db, user.id)]


@router.post("", status_code=201)
async def create_project_room(
    body: RoomCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await rooms.create_room(db, user.id, body.name, body.description)
    return rooms.room_to_dict(row)


@router.get("/{room_id}")
async def get_project_room(
    room_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await rooms.get_room(db, user.id, room_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project room not found")
    return rooms.room_to_dict(row)


@router.patch("/{room_id}")
async def patch_project_room(
    room_id: UUID,
    body: RoomPatch,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await rooms.update_room(db, user.id, room_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Project room not found")
    return rooms.room_to_dict(row)


@router.post("/{room_id}/link")
async def link_project_room_item(
    room_id: UUID,
    body: LinkBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked = await rooms.link_item(db, user.id, room_id, body.linked_type, body.linked_id)
    if linked is None:
        raise HTTPException(status_code=404, detail="Project room not found")
    return linked


@router.get("/{room_id}/summary")
async def project_room_summary(
    room_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    summary = await rooms.summarize_room(db, user.id, room_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Project room not found")
    return summary
