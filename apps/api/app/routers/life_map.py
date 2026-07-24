from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..services.brain_briefing_service import generate_life_map_briefing
from ..services.life_map_service import get_life_area_detail, get_life_map

router = APIRouter(tags=["life-map"])


@router.get("/life-map")
async def life_map(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_life_map(db, user.id)


@router.get("/life-map/briefing")
async def life_map_briefing(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await get_life_map(db, user.id)
    return await generate_life_map_briefing(db, user, life_map=payload)


@router.get("/life-map/{life_area}/briefing")
async def life_area_briefing(
    life_area: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await get_life_area_detail(db, user.id, life_area)
    if payload is None:
        raise HTTPException(status_code=404, detail="Life area not found")
    return await generate_life_map_briefing(db, user, life_map=payload, life_area=life_area)


@router.get("/life-map/{life_area}")
async def life_area_detail(
    life_area: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await get_life_area_detail(db, user.id, life_area)
    if payload is None:
        raise HTTPException(status_code=404, detail="Life area not found")
    return payload
