from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import FocusSession, Reflection, TodayItem
from .today_item_service import get_today_item


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def focus_session_to_dict(row: FocusSession) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": str(row.user_id),
        "today_item_id": str(row.today_item_id) if row.today_item_id else None,
        "title": row.title,
        "status": row.status,
        "started_at": row.started_at,
        "paused_at": row.paused_at,
        "ended_at": row.ended_at,
        "duration_seconds": row.duration_seconds,
        "notes": row.notes,
        "reflection_prompt": row.reflection_prompt,
        "metadata": row.metadata_json,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def start_focus_session(db: AsyncSession, user_id: uuid.UUID, today_item_id: uuid.UUID) -> FocusSession | None:
    item = await get_today_item(db, user_id, today_item_id)
    if item is None:
        return None
    now = _utcnow()
    metadata = dict(item.metadata_json or {})
    metadata["focus_started_at"] = now.isoformat()
    item.metadata_json = metadata
    item.status = "scheduled" if item.status == "open" else item.status
    item.updated_at = now
    row = FocusSession(user_id=user_id, today_item_id=item.id, title=item.title, started_at=now, status="active")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_focus_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> FocusSession | None:
    result = await db.execute(select(FocusSession).where(FocusSession.user_id == user_id, FocusSession.id == session_id))
    return result.scalar_one_or_none()


async def pause_focus_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> FocusSession | None:
    row = await get_focus_session(db, user_id, session_id)
    if row is None:
        return None
    if row.status == "active":
        row.status = "paused"
        row.paused_at = _utcnow()
        row.updated_at = _utcnow()
        await db.commit()
        await db.refresh(row)
    return row


async def resume_focus_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> FocusSession | None:
    row = await get_focus_session(db, user_id, session_id)
    if row is None:
        return None
    if row.status == "paused":
        row.status = "active"
        row.paused_at = None
        row.updated_at = _utcnow()
        await db.commit()
        await db.refresh(row)
    return row


async def end_focus_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID, notes: str | None = None) -> FocusSession | None:
    row = await get_focus_session(db, user_id, session_id)
    if row is None:
        return None
    now = _utcnow()
    row.status = "completed"
    row.ended_at = now
    row.duration_seconds = max(row.duration_seconds, int((now - _aware(row.started_at)).total_seconds()))
    row.notes = notes
    row.reflection_prompt = f"What helped you stay with “{row.title}”, and what should AiPal remember for next time?"
    row.updated_at = now
    if row.today_item_id:
        item = await db.get(TodayItem, row.today_item_id)
        if item is not None and item.user_id == user_id:
            item.status = "completed"
            metadata = dict(item.metadata_json or {})
            metadata["focus_completed_at"] = now.isoformat()
            metadata["duration_seconds"] = row.duration_seconds
            item.metadata_json = metadata
            item.updated_at = now
    db.add(
        Reflection(
            user_id=user_id,
            type="focus",
            summary=row.reflection_prompt,
            lessons=notes,
            metadata_json={"focus_session_id": str(row.id), "today_item_id": str(row.today_item_id) if row.today_item_id else None},
        )
    )
    await db.commit()
    await db.refresh(row)
    return row
