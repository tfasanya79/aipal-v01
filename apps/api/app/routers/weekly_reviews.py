from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import WeeklyReviewResponse
from ..services.weekly_review_service import generate_weekly_review, latest_weekly_review
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["reflections"], dependencies=[Depends(rate_limit_dependency("weekly_reviews", limit=30))])


@router.post("/reflections/weekly/generate", response_model=WeeklyReviewResponse)
async def generate_weekly(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return WeeklyReviewResponse(**await generate_weekly_review(db, user.id))


@router.get("/reflections/weekly/latest", response_model=WeeklyReviewResponse | None)
async def get_latest_weekly(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    latest = await latest_weekly_review(db, user.id)
    return WeeklyReviewResponse(**latest) if latest else None
