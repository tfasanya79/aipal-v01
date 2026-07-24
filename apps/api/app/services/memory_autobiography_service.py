from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from .memory_service import memory_timeline

_MILESTONE_TYPES = {"milestone", "important_event", "win", "achievement", "decision", "project"}


def _memory_date(memory) -> datetime:
    return memory.event_date or memory.created_at


def _memory_payload(memory) -> dict[str, Any]:
    date_value = _memory_date(memory)
    return {
        "id": str(memory.id),
        "date": date_value,
        "year": date_value.year,
        "month": date_value.month,
        "month_key": f"{date_value.year:04d}-{date_value.month:02d}",
        "type": memory.type,
        "life_area": memory.life_area,
        "title": memory.title,
        "content": memory.content,
        "importance": memory.importance,
        "sentiment": memory.sentiment,
        "is_milestone": memory.type in _MILESTONE_TYPES or int(memory.importance or 0) >= 4,
    }


async def get_memory_autobiography(db: AsyncSession, user_id: UUID, *, limit: int = 300) -> dict[str, Any]:
    memories = await memory_timeline(db, user_id, limit=limit)
    by_year: dict[int, dict[str, Any]] = {}
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    milestones: list[dict[str, Any]] = []

    for memory in memories:
        payload = _memory_payload(memory)
        year = int(payload["year"])
        month_key = str(payload["month_key"])
        by_month[month_key].append(payload)
        if payload["is_milestone"]:
            milestones.append(payload)
        if year not in by_year:
            by_year[year] = {"year": year, "months": [], "milestones": [], "item_count": 0}
        by_year[year]["item_count"] += 1
        if payload["is_milestone"]:
            by_year[year]["milestones"].append(payload)

    for year_data in by_year.values():
        months = []
        for month_key, items in sorted(by_month.items(), reverse=True):
            if not month_key.startswith(str(year_data["year"])):
                continue
            months.append(
                {
                    "month": month_key,
                    "items": items,
                    "milestones": [item for item in items if item["is_milestone"]],
                    "item_count": len(items),
                }
            )
        year_data["months"] = months

    years = sorted(by_year.values(), key=lambda row: row["year"], reverse=True)
    return {
        "status": "ok",
        "years": years,
        "milestones": milestones[:24],
        "total_items": len(memories),
    }
