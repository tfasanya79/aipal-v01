from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessProject, BusinessProjectEvent, Memory, Meeting, ProjectRoom, ProjectRoomLink, Task


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _matches(text: str | None, name: str) -> bool:
    if not text:
        return False
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None


def _room_business_ids(room: ProjectRoom) -> set[UUID]:
    return {room.business_project_id} if room.business_project_id else set()


def room_to_dict(row: ProjectRoom) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "business_project_id": str(row.business_project_id) if row.business_project_id else None,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "goals": row.goals,
        "key_people": row.key_people,
        "risks": row.risks,
        "opportunities": row.opportunities,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _find_business_project(db: AsyncSession, user_id: UUID, name: str) -> BusinessProject | None:
    result = await db.execute(
        select(BusinessProject)
        .where(BusinessProject.user_id == user_id, BusinessProject.name == name)
        .order_by(BusinessProject.updated_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_room(db: AsyncSession, user_id: UUID, name: str, description: str | None = None) -> ProjectRoom:
    clean_name = name.strip()
    business_project = await _find_business_project(db, user_id, clean_name)
    row = ProjectRoom(
        user_id=user_id,
        business_project_id=business_project.id if business_project else None,
        name=clean_name,
        description=description,
        status="active",
        goals=business_project.goals if business_project else None,
        key_people=business_project.key_people if business_project else None,
        risks=business_project.risks if business_project else None,
        opportunities=business_project.opportunities if business_project else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_rooms(db: AsyncSession, user_id: UUID) -> list[ProjectRoom]:
    result = await db.execute(
        select(ProjectRoom)
        .where(ProjectRoom.user_id == user_id)
        .order_by(ProjectRoom.updated_at.desc(), ProjectRoom.created_at.desc())
    )
    return list(result.scalars().all())


async def get_room(db: AsyncSession, user_id: UUID, room_id: UUID) -> ProjectRoom | None:
    result = await db.execute(select(ProjectRoom).where(ProjectRoom.user_id == user_id, ProjectRoom.id == room_id))
    return result.scalar_one_or_none()


async def update_room(db: AsyncSession, user_id: UUID, room_id: UUID, data: dict[str, Any]) -> ProjectRoom | None:
    row = await get_room(db, user_id, room_id)
    if row is None:
        return None
    for key in ("name", "description", "status", "goals", "key_people", "risks", "opportunities"):
        if key in data:
            setattr(row, key, data[key])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def link_item(db: AsyncSession, user_id: UUID, room_id: UUID, linked_type: str, linked_id: str) -> dict[str, Any] | None:
    room = await get_room(db, user_id, room_id)
    if room is None:
        return None
    existing = await db.execute(
        select(ProjectRoomLink).where(
            ProjectRoomLink.user_id == user_id,
            ProjectRoomLink.room_id == room_id,
            ProjectRoomLink.linked_type == linked_type,
            ProjectRoomLink.linked_id == linked_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is None:
        row = ProjectRoomLink(
            user_id=user_id,
            room_id=room_id,
            linked_type=linked_type,
            linked_id=linked_id,
            title=f"Linked {linked_type}",
        )
        db.add(row)
    await db.commit()
    return {"ok": True, "room_id": str(room_id), "linked_type": linked_type, "linked_id": linked_id}


async def _manual_links(db: AsyncSession, user_id: UUID, room_id: UUID) -> list[dict[str, Any]]:
    result = await db.execute(
        select(ProjectRoomLink)
        .where(ProjectRoomLink.user_id == user_id, ProjectRoomLink.room_id == room_id)
        .order_by(ProjectRoomLink.created_at.desc())
    )
    return [
        {
            "id": str(row.id),
            "linked_type": row.linked_type,
            "linked_id": row.linked_id,
            "title": row.title,
            "created_at": row.created_at,
        }
        for row in result.scalars().all()
    ]


async def _room_tasks(db: AsyncSession, user_id: UUID, room: ProjectRoom) -> list[dict[str, Any]]:
    result = await db.execute(select(Task).where(Task.user_id == user_id).order_by(Task.updated_at.desc()))
    return [
        {"id": row.id, "title": row.title, "status": row.status, "due_at": row.due_at}
        for row in result.scalars().all()
        if _matches(f"{row.title} {row.notes or ''}", room.name)
    ][:12]


async def _room_memories(db: AsyncSession, user_id: UUID, room: ProjectRoom) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.approval_status == "approved",
            Memory.user_approved.is_(True),
            Memory.paused.is_(False),
            or_(Memory.expires_at.is_(None), Memory.expires_at > _utcnow()),
        )
        .order_by(Memory.updated_at.desc())
    )
    return [
        {"id": str(row.id), "title": row.title, "type": row.type, "created_at": row.created_at}
        for row in result.scalars().all()
        if _matches(f"{row.title} {row.content}", room.name)
    ][:12]


async def _room_meetings(db: AsyncSession, user_id: UUID, room: ProjectRoom) -> list[dict[str, Any]]:
    business_ids = _room_business_ids(room)
    result = await db.execute(select(Meeting).where(Meeting.user_id == user_id).order_by(Meeting.start_time.desc()))
    return [
        {"id": str(row.id), "title": row.title, "start_time": row.start_time, "status": row.status}
        for row in result.scalars().all()
        if (row.project_id in business_ids) or _matches(f"{row.title} {row.notes or ''}", room.name)
    ][:12]


async def _room_events(db: AsyncSession, user_id: UUID, room: ProjectRoom) -> list[dict[str, Any]]:
    if not room.business_project_id:
        return []
    result = await db.execute(
        select(BusinessProjectEvent)
        .where(BusinessProjectEvent.user_id == user_id, BusinessProjectEvent.project_id == room.business_project_id)
        .order_by(BusinessProjectEvent.occurred_at.desc())
    )
    return [
        {"id": str(row.id), "title": row.title, "event_type": row.event_type, "occurred_at": row.occurred_at}
        for row in result.scalars().all()
    ][:12]


async def summarize_room(db: AsyncSession, user_id: UUID, room_id: UUID) -> dict[str, Any] | None:
    room = await get_room(db, user_id, room_id)
    if room is None:
        return None
    tasks = await _room_tasks(db, user_id, room)
    memories = await _room_memories(db, user_id, room)
    meetings = await _room_meetings(db, user_id, room)
    events = await _room_events(db, user_id, room)
    links = await _manual_links(db, user_id, room.id)
    return {
        "room": room_to_dict(room),
        "tasks": tasks,
        "memories": memories,
        "meetings": meetings,
        "events": events,
        "links": links,
        "progress": calculate_project_progress_from_items(tasks, meetings, events, links),
        "summary": (
            f"{room.name} has {len(tasks)} linked tasks, {len(meetings)} meetings, "
            f"{len(memories)} memories, {len(events)} events, and {len(links)} manual links."
        ),
    }


def calculate_project_progress_from_items(tasks: list[dict], meetings: list[dict], events: list[dict], links: list[dict] | None = None) -> int:
    links = links or []
    if not tasks and not meetings and not events and not links:
        return 0
    completed = len([task for task in tasks if task.get("status") in {"done", "completed"}])
    signal_count = len(tasks) + len(meetings) + len(events) + len(links)
    return min(100, int(((completed + len(events) + len(links)) / max(1, signal_count)) * 100))


async def calculate_project_progress(db: AsyncSession, user_id: UUID, room_id: UUID) -> int:
    summary = await summarize_room(db, user_id, room_id)
    return int(summary["progress"]) if summary else 0


async def auto_link_from_memory(db: AsyncSession, user_id: UUID, memory: Memory) -> ProjectRoom | None:
    for room in await list_rooms(db, user_id):
        if _matches(f"{memory.title} {memory.content}", room.name):
            return room
    return None


async def auto_link_from_task(db: AsyncSession, user_id: UUID, task: Task) -> ProjectRoom | None:
    for room in await list_rooms(db, user_id):
        if _matches(f"{task.title} {task.notes or ''}", room.name):
            return room
    return None


async def auto_link_from_meeting(db: AsyncSession, user_id: UUID, meeting: Meeting) -> ProjectRoom | None:
    for room in await list_rooms(db, user_id):
        if (meeting.project_id and meeting.project_id == room.business_project_id) or _matches(f"{meeting.title} {meeting.notes or ''}", room.name):
            return room
    return None
