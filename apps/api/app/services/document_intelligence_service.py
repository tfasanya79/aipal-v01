from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .connectors.document_connector import summarize_document_item
from .connectors_service import list_connected_items


async def summarize_document_item_service(title: str, content: str | None = None) -> str:
    return summarize_document_item(title, content)


async def import_document_item(db: AsyncSession, user_id: UUID, payload: dict) -> dict[str, object]:
    from .connectors_service import import_connected_item

    item = await import_connected_item(db, user_id, payload)
    return {"id": str(item.id), "title": item.title}


async def list_document_items(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    rows = await list_connected_items(db, user_id, provider="documents")
    return [{"id": str(row.id), "title": row.title, "content_summary": row.content_summary} for row in rows]

