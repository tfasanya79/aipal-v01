from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConnectedItem
from .connectors_service import create_commitment_from_item, list_connected_items
from .connectors.email_connector import summarize_email_item


async def summarize_email_item_service(title: str, snippet: str | None = None) -> str:
    return summarize_email_item(title, snippet)


async def extract_commitments(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    items = await list_connected_items(db, user_id, provider="email")
    out = []
    for item in items:
        if "deadline" in (item.content_summary or item.title).lower() or "follow" in (item.content_summary or item.title).lower():
            commitment = await create_commitment_from_item(db, user_id, item, "email_followup", item.title, due_at=item.occurred_at)
            out.append({"id": str(commitment.id), "title": commitment.title})
    return out


async def detect_followups(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    return await extract_commitments(db, user_id)


async def rank_importance(item: ConnectedItem) -> int:
    text = f"{item.title} {item.content_summary or ''}".lower()
    if any(word in text for word in ("urgent", "deadline", "reply", "action required")):
        return 9
    if any(word in text for word in ("follow", "meeting", "call", "demo")):
        return 7
    return 5


async def create_memory_candidates(item: ConnectedItem) -> list[dict[str, object]]:
    return [
        {
            "type": "important_event",
            "life_area": "business",
            "title": item.title,
            "content": item.content_summary or item.title,
            "importance": await rank_importance(item),
            "confidence": 0.75,
            "source_provider": item.provider,
            "source_item_id": item.id,
        }
    ]

