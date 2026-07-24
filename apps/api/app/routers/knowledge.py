from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..services.knowledge_graph_service import (
    get_entity,
    get_entity_graph,
    get_user_graph_summary,
    rebuild_user_graph,
    search_entities,
)

router = APIRouter(tags=["knowledge"], dependencies=[Depends(rate_limit_dependency("knowledge", limit=60))])


@router.get("/knowledge/entities")
async def list_entities(
    entity_type: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entities = await search_entities(db, user.id, "", entity_type=entity_type)
    return [
        {
            "id": str(entity.id),
            "user_id": str(entity.user_id),
            "entity_type": entity.entity_type,
            "name": entity.name,
            "aliases": entity.aliases,
            "description": entity.description,
            "metadata": entity.metadata_json,
            "confidence": float(entity.confidence or 0.0),
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
        for entity in entities
    ]


@router.get("/knowledge/entities/{entity_id}")
async def get_entity_route(
    entity_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entity = await get_entity(db, user.id, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return {
        "id": str(entity.id),
        "user_id": str(entity.user_id),
        "entity_type": entity.entity_type,
        "name": entity.name,
        "aliases": entity.aliases,
        "description": entity.description,
        "metadata": entity.metadata_json,
        "confidence": float(entity.confidence or 0.0),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


@router.get("/knowledge/entities/{entity_id}/graph")
async def get_entity_graph_route(
    entity_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    graph = await get_entity_graph(db, user.id, entity_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return graph


@router.get("/knowledge/search")
async def search_knowledge(
    query: str = Query(default=""),
    entity_type: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    entities = await search_entities(db, user.id, query, entity_type=entity_type)
    return [
        {
            "id": str(entity.id),
            "user_id": str(entity.user_id),
            "entity_type": entity.entity_type,
            "name": entity.name,
            "aliases": entity.aliases,
            "description": entity.description,
            "metadata": entity.metadata_json,
            "confidence": float(entity.confidence or 0.0),
            "created_at": entity.created_at,
            "updated_at": entity.updated_at,
        }
        for entity in entities
    ]


@router.get("/knowledge/summary")
async def knowledge_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_user_graph_summary(db, user.id)


@router.post("/knowledge/rebuild")
async def rebuild_knowledge(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await rebuild_user_graph(db, user.id)
