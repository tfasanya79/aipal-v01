from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import CommitmentCreate, CommitmentResponse, CommitmentUpdate
from ..services.commitment_service import (
    commitment_to_dict,
    create_commitment,
    dismiss,
    list_commitments,
    list_due_followups,
    mark_completed,
    update_commitment,
)

router = APIRouter(tags=["commitments"], dependencies=[Depends(rate_limit_dependency("commitments", limit=60))])


@router.get("/commitments", response_model=list[CommitmentResponse])
async def get_commitments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [CommitmentResponse(**commitment_to_dict(row)) for row in await list_commitments(db, user.id)]


@router.get("/commitments/due", response_model=list[CommitmentResponse])
async def get_due_commitments(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [CommitmentResponse(**commitment_to_dict(row)) for row in await list_due_followups(db, user.id)]


@router.post("/commitments", response_model=CommitmentResponse)
async def post_commitment(
    body: CommitmentCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await create_commitment(
        db,
        user.id,
        title=body.title,
        content=body.content,
        due_at=body.due_at,
        confidence=body.confidence,
        source_message_id=body.source_message_id,
        source_memory_id=body.source_memory_id,
        follow_up_at=body.follow_up_at,
    )
    return CommitmentResponse(**commitment_to_dict(row))


@router.patch("/commitments/{commitment_id}", response_model=CommitmentResponse)
async def patch_commitment(
    commitment_id: UUID,
    body: CommitmentUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await update_commitment(db, user.id, commitment_id, body.model_dump(exclude_none=True))
    if row is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return CommitmentResponse(**commitment_to_dict(row))


@router.post("/commitments/{commitment_id}/complete", response_model=CommitmentResponse)
async def complete_commitment(
    commitment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await mark_completed(db, user.id, commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return CommitmentResponse(**commitment_to_dict(row))


@router.post("/commitments/{commitment_id}/dismiss", response_model=CommitmentResponse)
async def dismiss_commitment(
    commitment_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await dismiss(db, user.id, commitment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Commitment not found")
    return CommitmentResponse(**commitment_to_dict(row))
