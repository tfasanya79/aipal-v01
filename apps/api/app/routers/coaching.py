from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import (
    CoachingDecisionRequest,
    CoachingDecisionResponse,
    CoachingDecisionSummary,
    FrameworkListResponse,
    FrameworkRequest,
    FrameworkResponse,
)
from ..services.coaching_service import (
    analyze_decision,
    apply_framework,
    get_decision,
    list_decisions,
)
from ..services.thinking_framework_service import list_frameworks

router = APIRouter(prefix="/coaching", tags=["coaching"], dependencies=[Depends(rate_limit_dependency("coaching", limit=60))])


def _decision_summary(decision) -> CoachingDecisionSummary:
    return CoachingDecisionSummary(
        id=decision.id,
        title=decision.title,
        question=decision.question,
        options=decision.options,
        selected_option=decision.selected_option,
        framework=decision.framework,
        analysis=decision.analysis,
        recommendation=decision.recommendation,
        confidence=float(decision.confidence) if decision.confidence is not None else None,
        status=decision.status,
        created_at=decision.created_at,
        updated_at=decision.updated_at,
    )


@router.post("/decision", response_model=CoachingDecisionResponse)
async def coaching_decision(
    body: CoachingDecisionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await analyze_decision(db, user.id, body.question, body.options)
    return CoachingDecisionResponse(**result)


@router.get("/decisions", response_model=list[CoachingDecisionSummary])
async def coaching_decisions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [_decision_summary(decision) for decision in await list_decisions(db, user.id)]


@router.get("/decisions/{decision_id}", response_model=CoachingDecisionSummary)
async def coaching_decision_detail(
    decision_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    decision = await get_decision(db, user.id, decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return _decision_summary(decision)


@router.post("/framework", response_model=FrameworkResponse)
async def coaching_framework(
    body: FrameworkRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await apply_framework(db, user.id, body.framework, body.prompt)
    return FrameworkResponse(framework=result["framework"], output=result["output"])


@router.get("/frameworks", response_model=FrameworkListResponse)
async def coaching_frameworks(
    user: User = Depends(get_current_user),
):
    return FrameworkListResponse(frameworks=list_frameworks())
