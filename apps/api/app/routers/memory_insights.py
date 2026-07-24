from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import MemoryTimelineItem, MemoryTimelineResponse
from ..services.memory_autobiography_service import get_memory_autobiography
from ..services.memory_service import memory_timeline
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["memory"], dependencies=[Depends(rate_limit_dependency("memory", limit=60))])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


@router.get("/memory/timeline", response_model=MemoryTimelineResponse)
async def timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    life_area: str | None = None,
    type: str | None = Query(default=None),
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
):
    memories = await memory_timeline(
        db,
        user.id,
        life_area=life_area,
        type=type,
        start_date=_parse_dt(start_date),
        end_date=_parse_dt(end_date),
        limit=max(1, min(limit, 200)),
    )
    return MemoryTimelineResponse(
        items=[
            MemoryTimelineItem(
                id=memory.id,
                date=memory.event_date or memory.created_at,
                type=memory.type,
                life_area=memory.life_area,
                title=memory.title,
                content=memory.content,
                importance=memory.importance,
                sentiment=memory.sentiment,
                entities=list(memory.entities or []) if isinstance(memory.entities, list) else None,
                follow_up_at=memory.follow_up_at,
                follow_up_status=memory.follow_up_status,
                follow_up_prompt=memory.follow_up_prompt,
            )
            for memory in memories
        ]
    )


@router.get("/memory/autobiography")
async def autobiography(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 300,
):
    return await get_memory_autobiography(db, user.id, limit=max(1, min(limit, 500)))
