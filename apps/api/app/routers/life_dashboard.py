from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import LifeDashboardResponse
from ..services.life_dashboard_service import get_life_dashboard, get_living_dashboard

router = APIRouter(tags=["life-dashboard"], dependencies=[Depends(rate_limit_dependency("life_dashboard", limit=40))])


@router.get("/life-dashboard", response_model=LifeDashboardResponse)
async def life_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return LifeDashboardResponse(**await get_life_dashboard(db, user.id))


@router.get("/life-dashboard/living")
async def living_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await get_living_dashboard(db, user.id)
