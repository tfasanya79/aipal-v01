from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import HabitCreateRequest, HabitLogRequest, HabitLogResponse, HabitResponse, HabitSummaryResponse
from ..services.habit_service import create_habit, list_habits, log_habit, summarize_habits

router = APIRouter(prefix="/habits", tags=["habits"], dependencies=[Depends(rate_limit_dependency("habits", limit=40))])


def _habit_response(habit) -> HabitResponse:
    return HabitResponse(
        id=habit.id,
        name=habit.name,
        life_area=habit.life_area,
        frequency=habit.frequency,
        target_count=habit.target_count,
        status=habit.status,
        created_at=habit.created_at,
        updated_at=habit.updated_at,
    )


@router.post("", response_model=HabitResponse)
async def create_habit_route(
    body: HabitCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    habit = await create_habit(db, user.id, body.name, body.life_area, body.frequency, body.target_count)
    return _habit_response(habit)


@router.get("", response_model=list[HabitResponse])
async def list_habits_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return [_habit_response(habit) for habit in await list_habits(db, user.id)]


@router.post("/{habit_id}/log", response_model=HabitLogResponse)
async def log_habit_route(
    habit_id: UUID,
    body: HabitLogRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    log = await log_habit(db, user.id, habit_id, value=body.value, note=body.note, source=body.source)
    if log is None:
        raise HTTPException(status_code=404, detail="Habit not found")
    return HabitLogResponse(
        id=log.id,
        habit_id=log.habit_id,
        logged_at=log.logged_at,
        value=log.value,
        note=log.note,
        source=log.source,
        created_at=log.created_at,
    )


@router.get("/summary", response_model=HabitSummaryResponse)
async def habits_summary_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return HabitSummaryResponse(**await summarize_habits(db, user.id))
