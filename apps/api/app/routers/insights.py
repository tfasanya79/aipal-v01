from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..schemas import CompanionScoreResponse, EmotionalContinuityResponse, LifeAreaInsightsResponse
from ..services.ai_insights_service import (
    generate_life_area_insights,
    generate_monthly_insights,
    generate_weekly_insights,
)
from ..services.brain_briefing_service import generate_insight_briefing
from ..services.companion_score_service import get_companion_score
from ..services.emotional_continuity_service import get_emotional_continuity
from ..services.life_area_service import get_life_area_insights
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["insights"], dependencies=[Depends(rate_limit_dependency("insights", limit=60))])


@router.get("/insights/life-areas", response_model=LifeAreaInsightsResponse)
async def life_areas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return LifeAreaInsightsResponse(areas=await get_life_area_insights(db, user.id))


@router.get("/insights/companion-score", response_model=CompanionScoreResponse)
async def companion_score(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return CompanionScoreResponse(**await get_companion_score(db, user.id))


@router.get("/insights/emotional-continuity", response_model=EmotionalContinuityResponse)
async def emotional_continuity(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return EmotionalContinuityResponse(**await get_emotional_continuity(db, user.id))


@router.get("/insights/weekly")
async def weekly_insights(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await generate_weekly_insights(db, user.id)
    payload["narrative"] = await generate_insight_briefing(db, user, insight_type="weekly", metrics=payload)
    return payload


@router.get("/insights/monthly")
async def monthly_insights(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await generate_monthly_insights(db, user.id)
    payload["narrative"] = await generate_insight_briefing(db, user, insight_type="monthly", metrics=payload)
    return payload


@router.get("/insights/life-areas/deep")
async def deep_life_area_insights(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await generate_life_area_insights(db, user.id)
    payload["narrative"] = await generate_insight_briefing(db, user, insight_type="life_area", metrics=payload)
    return payload
