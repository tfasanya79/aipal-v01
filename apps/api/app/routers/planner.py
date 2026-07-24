from __future__ import annotations

from datetime import date as date_type
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services import planner_engine_service as planner

router = APIRouter(prefix="/planner", tags=["planner"])


class DateBody(BaseModel):
    date: date_type | None = None
    week_start: date_type | None = None
    month: str | None = None
    quarter: str | None = None
    goal_id: UUID | None = None


@router.post("/daily")
async def daily_plan(
    body: DateBody = DateBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_daily_plan(db, user, body.date)


@router.post("/weekly")
async def weekly_plan(
    body: DateBody = DateBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_weekly_plan(db, user, body.week_start)


@router.post("/monthly")
async def monthly_plan(
    body: DateBody = DateBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_monthly_plan(db, user, body.month)


@router.post("/quarterly")
async def quarterly_plan(
    body: DateBody = DateBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_quarterly_plan(db, user, body.quarter)


@router.post("/90-day")
async def ninety_day_plan(
    body: DateBody = DateBody(),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_90_day_plan(db, user, body.goal_id)


@router.post("/goal-roadmap")
async def goal_roadmap(
    body: DateBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.goal_id is None:
        raise HTTPException(status_code=422, detail="goal_id is required")
    return await planner.generate_goal_roadmap(db, user, body.goal_id)


@router.post("/life-roadmap")
async def life_roadmap(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await planner.generate_life_roadmap(db, user)


@router.post("/{draft_id}/confirm")
async def confirm_plan(
    draft_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    created = await planner.convert_plan_to_today_items(db, user, draft_id)
    return {"ok": True, "created": created}
