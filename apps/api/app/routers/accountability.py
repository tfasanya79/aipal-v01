from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import AccountabilityCompareRequest, AccountabilitySnapshotRequest, AccountabilitySnapshotResponse
from ..services.accountability_service import (
    compare_periods,
    generate_accountability_prompt,
    generate_accountability_snapshot,
    latest_accountability_snapshot,
)

router = APIRouter(prefix="/accountability", tags=["accountability"], dependencies=[Depends(rate_limit_dependency("accountability", limit=40))])


def _snapshot_response(snapshot) -> AccountabilitySnapshotResponse:
    return AccountabilitySnapshotResponse(
        id=snapshot.id,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        goals_summary=snapshot.goals_summary,
        tasks_summary=snapshot.tasks_summary,
        habits_summary=snapshot.habits_summary,
        blockers=snapshot.blockers,
        score=float(snapshot.score) if snapshot.score is not None else None,
        reflection=snapshot.reflection,
        created_at=snapshot.created_at,
    )


@router.post("/snapshot", response_model=AccountabilitySnapshotResponse)
async def snapshot_route(
    body: AccountabilitySnapshotRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await generate_accountability_snapshot(db, user.id, body.period_start, body.period_end)
    return _snapshot_response(snapshot)


@router.get("/latest", response_model=AccountabilitySnapshotResponse | dict)
async def latest_snapshot_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await latest_accountability_snapshot(db, user.id)
    if snapshot is None:
        prompt = await generate_accountability_prompt(db, user.id)
        return {"message": "No accountability snapshot yet.", "prompt": prompt}
    return _snapshot_response(snapshot)


@router.post("/compare")
async def compare_route(
    body: AccountabilityCompareRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await compare_periods(
        db,
        user.id,
        (body.previous_period_start, body.previous_period_end),
        (body.current_period_start, body.current_period_end),
    )
