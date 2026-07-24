from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import BusinessProjectCreate, BusinessProjectEventResponse, BusinessProjectResponse
from ..services.business_context_service import create_project, get_project, list_events, list_projects, update_project

router = APIRouter(prefix="/business", tags=["business"], dependencies=[Depends(rate_limit_dependency("business", limit=30))])


def _project(row) -> BusinessProjectResponse:
    return BusinessProjectResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        status=row.status,
        goals=row.goals,
        key_people=row.key_people,
        risks=row.risks,
        opportunities=row.opportunities,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _event(row) -> BusinessProjectEventResponse:
    return BusinessProjectEventResponse(
        id=row.id,
        project_id=row.project_id,
        event_type=row.event_type,
        title=row.title,
        description=row.description,
        occurred_at=row.occurred_at,
        source_type=row.source_type,
        source_id=row.source_id,
        created_at=row.created_at,
    )


@router.get("/projects", response_model=list[BusinessProjectResponse])
async def projects(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_project(row) for row in await list_projects(db, user.id)]


@router.post("/projects", response_model=BusinessProjectResponse)
async def create(body: BusinessProjectCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _project(await create_project(db, user.id, body.model_dump()))


@router.get("/projects/{project_id}", response_model=BusinessProjectResponse)
async def detail(project_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await get_project(db, user.id, project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project(row)


@router.patch("/projects/{project_id}", response_model=BusinessProjectResponse)
async def patch(project_id: UUID, body: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await update_project(db, user.id, project_id, body)
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return _project(row)


@router.get("/projects/{project_id}/events", response_model=list[BusinessProjectEventResponse])
async def events(project_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_event(row) for row in await list_events(db, user.id, project_id)]
