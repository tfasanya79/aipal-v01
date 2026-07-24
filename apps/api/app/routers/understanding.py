from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import UnderstandingProfileResponse
from ..services.long_term_understanding_service import get_understanding_profile

router = APIRouter(tags=["understanding"], dependencies=[Depends(rate_limit_dependency("understanding", limit=40))])


@router.get("/understanding/profile", response_model=UnderstandingProfileResponse)
async def understanding_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return UnderstandingProfileResponse(**await get_understanding_profile(db, user.id))

