from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Meeting, MeetingNote, User
from .brain_briefing_service import generate_notification_briefing
from .today_item_service import create_from_meeting, today_item_to_dict


def meeting_to_dict(row: Meeting) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "title": row.title,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "participants": row.participants,
        "location": row.location,
        "meeting_link": row.meeting_link,
        "project_id": str(row.project_id) if row.project_id else None,
        "notes": row.notes,
        "status": row.status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def note_to_dict(row: MeetingNote) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "meeting_id": str(row.meeting_id),
        "content": row.content,
        "summary": row.summary,
        "decisions": row.decisions,
        "action_items": row.action_items,
        "followups": row.followups,
        "created_at": row.created_at,
    }


async def create_today_items_from_meeting(db: AsyncSession, user_id: UUID, meeting: Meeting):
    item = await create_from_meeting(
        db,
        user_id,
        title=meeting.title,
        start_time=meeting.start_time,
        end_time=meeting.end_time,
        description=meeting.notes,
        calendar_event_id=meeting.id,
        source="meeting",
    )
    return today_item_to_dict(item)


async def create_meeting(db: AsyncSession, user_id: UUID, payload: dict[str, Any]) -> Meeting:
    row = Meeting(
        user_id=user_id,
        title=str(payload.get("title") or "Meeting").strip(),
        start_time=payload["start_time"],
        end_time=payload.get("end_time"),
        participants=payload.get("participants"),
        location=payload.get("location"),
        meeting_link=payload.get("meeting_link"),
        project_id=payload.get("project_id"),
        notes=payload.get("notes"),
        status=payload.get("status") or "scheduled",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await create_today_items_from_meeting(db, user_id, row)
    return row


async def list_meetings(db: AsyncSession, user_id: UUID) -> list[Meeting]:
    result = await db.execute(
        select(Meeting).where(Meeting.user_id == user_id).order_by(Meeting.start_time.asc())
    )
    return list(result.scalars().all())


async def list_upcoming_meetings(db: AsyncSession, user_id: UUID) -> list[Meeting]:
    result = await db.execute(
        select(Meeting)
        .where(
            Meeting.user_id == user_id,
            Meeting.status != "cancelled",
            Meeting.start_time >= datetime.now(UTC),
        )
        .order_by(Meeting.start_time.asc())
    )
    return list(result.scalars().all())


async def get_meeting(db: AsyncSession, user_id: UUID, meeting_id: UUID) -> Meeting | None:
    result = await db.execute(select(Meeting).where(Meeting.user_id == user_id, Meeting.id == meeting_id))
    return result.scalar_one_or_none()


async def update_meeting(db: AsyncSession, user_id: UUID, meeting_id: UUID, payload: dict[str, Any]) -> Meeting | None:
    row = await get_meeting(db, user_id, meeting_id)
    if row is None:
        return None
    for key in ("title", "start_time", "end_time", "participants", "location", "meeting_link", "project_id", "notes", "status"):
        if key in payload and payload[key] is not None:
            setattr(row, key, payload[key])
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    await create_today_items_from_meeting(db, user_id, row)
    return row


async def prepare_meeting_brief(db: AsyncSession, user: User, meeting_id: UUID) -> dict[str, Any] | None:
    meeting = await get_meeting(db, user.id, meeting_id)
    if meeting is None:
        return None
    participants = meeting.participants or []
    context = (
        f"Meeting: {meeting.title}\n"
        f"Time: {meeting.start_time.isoformat()}\n"
        f"Participants: {participants}\n"
        f"Notes: {(meeting.notes or '')[:800]}"
    )
    brief = await generate_notification_briefing(
        db,
        user,
        user_message="Prepare me for this meeting in a warm, concise way. Mention only provided context.",
        trigger_context=context,
    )
    return {"meeting": meeting_to_dict(meeting), "brief": brief.get("message") or ""}


def _summarize_text(text: str) -> str:
    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    return ". ".join(sentences[:2]) + ("." if sentences else "")


def _extract_action_items(text: str) -> list[dict[str, str]]:
    markers = ("todo", "follow up", "send", "call", "prepare", "share", "confirm")
    items = []
    chunks = []
    for raw_line in text.splitlines():
        chunks.extend(part for part in raw_line.split(".") if part.strip())
    for raw in chunks:
        line = raw.strip(" -•\t")
        if not line:
            continue
        if any(marker in line.lower() for marker in markers):
            items.append({"title": line[:180], "status": "draft"})
    return items[:8]


async def create_meeting_notes(db: AsyncSession, user_id: UUID, meeting_id: UUID, notes: str) -> MeetingNote | None:
    meeting = await get_meeting(db, user_id, meeting_id)
    if meeting is None:
        return None
    summary = _summarize_text(notes)
    action_items = _extract_action_items(notes)
    followups = [item for item in action_items if "follow" in item["title"].lower()]
    row = MeetingNote(
        user_id=user_id,
        meeting_id=meeting_id,
        content=notes,
        summary=summary,
        decisions=[],
        action_items=action_items,
        followups=followups,
    )
    meeting.notes = notes
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def summarize_meeting(db: AsyncSession, user_id: UUID, meeting_id: UUID) -> dict[str, Any] | None:
    result = await db.execute(
        select(MeetingNote).where(MeetingNote.user_id == user_id, MeetingNote.meeting_id == meeting_id).order_by(MeetingNote.created_at.desc())
    )
    note = result.scalars().first()
    if note is None:
        return None
    return note_to_dict(note)


async def extract_action_items(db: AsyncSession, user_id: UUID, meeting_id: UUID) -> list[dict[str, str]] | None:
    summary = await summarize_meeting(db, user_id, meeting_id)
    if summary is None:
        return None
    return list(summary.get("action_items") or [])


async def create_followups_from_meeting(db: AsyncSession, user_id: UUID, meeting_id: UUID) -> list[dict[str, str]] | None:
    items = await extract_action_items(db, user_id, meeting_id)
    if items is None:
        return None
    return [item for item in items if "follow" in item["title"].lower()]
