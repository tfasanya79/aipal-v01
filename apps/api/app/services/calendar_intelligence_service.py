from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .connectors_service import create_commitment_from_item, list_connected_items
from .connectors.calendar_connector import summarize_calendar_item


async def summarize_calendar_item_service(title: str, attendees: list[str] | None = None) -> str:
    return summarize_calendar_item(title, attendees)


async def sync_calendar_commitments(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    items = await list_connected_items(db, user_id, provider="calendar")
    out = []
    for item in items:
        commitment = await create_commitment_from_item(db, user_id, item, "meeting", item.title, due_at=item.occurred_at)
        out.append({"id": str(commitment.id), "title": commitment.title})
    return out


async def list_calendar_commitments(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    from .connectors_service import list_commitments

    rows = await list_commitments(db, user_id)
    return [{"id": str(row.id), "title": row.title, "due_at": row.due_at, "status": row.status} for row in rows]

