from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BusinessProject, BusinessProjectEvent

_PROJECT_HINTS = {
    "qring": "Qring",
    "campuscart": "CampusCart",
    "fitaccess": "FitAccess",
    "aipal": "AiPal",
}

_PROJECT_CONTEXT_HINTS = (
    "demo",
    "launch",
    "meeting",
    "customer",
    "client",
    "sales",
    "pitch",
    "deadline",
    "project",
    "build",
    "ship",
    "investor",
    "pipeline",
    "follow-up",
    "follow up",
    "customer",
)


def _text_has_whole_term(text: str, term: str) -> bool:
    if not text or not term:
        return False
    pattern = rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _text_matches_project(text: str, project_name: str) -> bool:
    if _text_has_whole_term(text, project_name):
        return True
    compact_text = re.sub(r"[^a-z0-9]+", "", text.lower())
    compact_name = re.sub(r"[^a-z0-9]+", "", project_name.lower())
    if not compact_name or len(compact_name) < 5:
        return False
    return compact_name == compact_text or compact_name in compact_text


def _has_project_context(text: str) -> bool:
    lower = text.lower()
    return any(hint in lower for hint in _PROJECT_CONTEXT_HINTS)


async def list_projects(db: AsyncSession, user_id: UUID) -> list[BusinessProject]:
    result = await db.execute(
        select(BusinessProject).where(BusinessProject.user_id == user_id).order_by(BusinessProject.created_at.desc())
    )
    return list(result.scalars().all())


async def get_project(db: AsyncSession, user_id: UUID, project_id: UUID) -> BusinessProject | None:
    result = await db.execute(
        select(BusinessProject).where(BusinessProject.user_id == user_id, BusinessProject.id == project_id)
    )
    return result.scalar_one_or_none()


async def create_project(db: AsyncSession, user_id: UUID, data: dict) -> BusinessProject:
    row = BusinessProject(user_id=user_id, **data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def update_project(db: AsyncSession, user_id: UUID, project_id: UUID, data: dict) -> BusinessProject | None:
    row = await get_project(db, user_id, project_id)
    if row is None:
        return None
    for key in ("name", "description", "status", "goals", "key_people", "risks", "opportunities"):
        if key in data and data[key] is not None:
            setattr(row, key, data[key])
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def list_events(db: AsyncSession, user_id: UUID, project_id: UUID) -> list[BusinessProjectEvent]:
    result = await db.execute(
        select(BusinessProjectEvent)
        .where(BusinessProjectEvent.user_id == user_id, BusinessProjectEvent.project_id == project_id)
        .order_by(BusinessProjectEvent.occurred_at.desc())
    )
    return list(result.scalars().all())


async def create_event(db: AsyncSession, user_id: UUID, project_id: UUID, data: dict) -> BusinessProjectEvent:
    row = BusinessProjectEvent(user_id=user_id, project_id=project_id, **data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def match_project_for_text(db: AsyncSession, user_id: UUID, text: str) -> BusinessProject | None:
    if not text.strip():
        return None

    existing = await list_projects(db, user_id)
    for project in existing:
        if _text_matches_project(text, project.name):
            return project

    if not _has_project_context(text):
        return None

    for key, name in _PROJECT_HINTS.items():
        if _text_matches_project(text, name) or _text_has_whole_term(text, key):
            return await get_or_create_project(db, user_id, name)
    return None


async def get_or_create_project(db: AsyncSession, user_id: UUID, name: str) -> BusinessProject:
    result = await db.execute(
        select(BusinessProject).where(BusinessProject.user_id == user_id, BusinessProject.name == name)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = BusinessProject(user_id=user_id, name=name, status="active")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


async def summarize_project_context(db: AsyncSession, user_id: UUID) -> list[dict[str, object]]:
    projects = await list_projects(db, user_id)
    return [
        {
            "id": str(project.id),
            "name": project.name,
            "status": project.status,
            "description": project.description,
        }
        for project in projects
    ]
