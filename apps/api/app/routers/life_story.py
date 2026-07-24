from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import LifeStoryResponse
from ..services.life_story_service import get_life_story

router = APIRouter(prefix="/life-story", tags=["life-story"], dependencies=[Depends(rate_limit_dependency("life_story", limit=40))])


@router.get("/accomplishments", response_model=LifeStoryResponse)
async def accomplishments(period: str = "year", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return LifeStoryResponse(**await get_life_story(db, user.id, period))


@router.get("/patterns", response_model=LifeStoryResponse)
async def patterns(period: str = "year", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return LifeStoryResponse(**await get_life_story(db, user.id, period))


@router.get("/strengths", response_model=LifeStoryResponse)
async def strengths(period: str = "year", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return LifeStoryResponse(**await get_life_story(db, user.id, period))


@router.get("/growth-summary", response_model=LifeStoryResponse)
async def growth_summary(period: str = "year", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return LifeStoryResponse(**await get_life_story(db, user.id, period))

