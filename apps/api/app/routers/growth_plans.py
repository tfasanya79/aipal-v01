from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import GrowthPlanRequest, GrowthPlanResponse, GrowthPlanUpdateRequest
from ..services.growth_plan_service import create_growth_plan, get_growth_plan, list_growth_plans, update_growth_plan

router = APIRouter(prefix="/growth-plans", tags=["growth-plans"], dependencies=[Depends(rate_limit_dependency("growth_plans", limit=40))])


def _to_response(plan) -> GrowthPlanResponse:
    return GrowthPlanResponse(
        id=plan.id,
        goal_id=plan.goal_id,
        title=plan.title,
        horizon=plan.horizon,
        summary=plan.summary,
        milestones=plan.milestones,
        weekly_focus=plan.weekly_focus,
        risks=plan.risks,
        success_metrics=plan.success_metrics,
        status=plan.status,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


@router.post("", response_model=GrowthPlanResponse)
async def create_growth_plan_route(
    body: GrowthPlanRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        plan = await create_growth_plan(db, user.id, goal_id=body.goal_id, horizon=body.horizon, title=body.title)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(plan)


@router.get("", response_model=list[GrowthPlanResponse])
async def list_growth_plans_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [_to_response(plan) for plan in await list_growth_plans(db, user.id)]


@router.get("/{plan_id}", response_model=GrowthPlanResponse)
async def get_growth_plan_route(
    plan_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await get_growth_plan(db, user.id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return _to_response(plan)


@router.patch("/{plan_id}", response_model=GrowthPlanResponse)
async def patch_growth_plan_route(
    plan_id: UUID,
    body: GrowthPlanUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await update_growth_plan(db, user.id, plan_id, body.model_dump(exclude_none=True))
    if plan is None:
        raise HTTPException(status_code=404, detail="Growth plan not found")
    return _to_response(plan)
