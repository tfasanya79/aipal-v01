from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import FollowUpResponse
from ..services.memory_service import memory_to_dict
from ..services.relationship_followup_service import (
    dismiss_followup,
    generate_followup_prompt,
    list_due_followups,
    mark_followup_completed,
)
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["relationship"], dependencies=[Depends(rate_limit_dependency("relationship", limit=60))])


@router.get("/relationship/followups/due", response_model=list[FollowUpResponse])
async def get_due_followups(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memories = await list_due_followups(db, user.id)
    return [
        FollowUpResponse(
            id=memory.id,
            title=memory.title,
            type=memory.type,
            life_area=memory.life_area,
            prompt=generate_followup_prompt(memory),
            follow_up_at=memory.follow_up_at,
            event_date=memory.event_date,
            follow_up_status=memory.follow_up_status,
            importance=memory.importance,
            sentiment=memory.sentiment,
            entities=list(memory.entities or []) if isinstance(memory.entities, list) else None,
        )
        for memory in memories
    ]


@router.post("/relationship/followups/{memory_id}/complete")
async def complete_followup(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await mark_followup_completed(db, user.id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.post("/relationship/followups/{memory_id}/dismiss")
async def dismiss_followup_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await dismiss_followup(db, user.id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}
