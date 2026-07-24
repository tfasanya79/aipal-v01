from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import User
from ..rate_limit import rate_limit_dependency
from ..schemas import CompanionPreferenceResponse, CompanionPreferenceUpdate, ProactivePromptGenerateRequest, ProactivePromptResponse
from ..services.proactive_conversation_service import (
    dismiss_proactive,
    generate_proactive_prompt,
    get_or_create_preferences,
    list_proactive_prompts,
    mark_proactive_delivered,
    update_preferences,
)
from ..services.brain_briefing_service import generate_proactive_prompt_wording

router = APIRouter(prefix="/proactive", tags=["proactive"], dependencies=[Depends(rate_limit_dependency("proactive", limit=40))])


def _prompt(row) -> ProactivePromptResponse:
    return ProactivePromptResponse(
        id=row.id,
        trigger_type=row.trigger_type,
        prompt=row.prompt,
        trigger_metadata=row.trigger_metadata,
        source_type=row.source_type,
        source_id=row.source_id,
        status=row.status,
        priority=row.priority,
        scheduled_for=row.scheduled_for,
        delivered_at=row.delivered_at,
        dismissed_at=row.dismissed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/prompts", response_model=list[ProactivePromptResponse])
async def get_prompts(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return [_prompt(row) for row in await list_proactive_prompts(db, user.id)]


@router.post("/prompts/generate")
async def generate_prompt(body: ProactivePromptGenerateRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await generate_proactive_prompt(db, user.id, force=body.force)
    if row is None:
        return {"message": "No proactive prompt available."}
    return _prompt(row)


@router.post("/prompts/{prompt_id}/delivered", response_model=ProactivePromptResponse)
async def delivered(prompt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await mark_proactive_delivered(db, user.id, prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt(row)


@router.post("/prompts/{prompt_id}/wording")
async def prompt_wording(prompt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await list_proactive_prompts(db, user.id)
    row = next((item for item in rows if item.id == prompt_id), None)
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return await generate_proactive_prompt_wording(
        db,
        user,
        trigger_type=row.trigger_type,
        context=str(row.trigger_metadata or {"prompt": row.prompt}),
    )


@router.post("/prompts/{prompt_id}/dismiss", response_model=ProactivePromptResponse)
async def dismiss(prompt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await dismiss_proactive(db, user.id, prompt_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt(row)


@router.get("/companion/preferences", response_model=CompanionPreferenceResponse)
async def get_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await get_or_create_preferences(db, user.id)
    return CompanionPreferenceResponse(
        proactive_enabled=row.proactive_enabled,
        max_proactive_per_day=row.max_proactive_per_day,
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
        tone=row.tone,
        humor_level=row.humor_level,
        directness_level=row.directness_level,
        voice_pace=row.voice_pace,
        tts_voice=row.tts_voice,
        voice_profile=row.tts_voice,
        response_length=row.response_length,
    )


@router.patch("/companion/preferences", response_model=CompanionPreferenceResponse)
async def patch_preferences(body: CompanionPreferenceUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await update_preferences(db, user.id, body.model_dump(exclude_none=True))
    return CompanionPreferenceResponse(
        proactive_enabled=row.proactive_enabled,
        max_proactive_per_day=row.max_proactive_per_day,
        quiet_hours_start=row.quiet_hours_start,
        quiet_hours_end=row.quiet_hours_end,
        tone=row.tone,
        humor_level=row.humor_level,
        directness_level=row.directness_level,
        voice_pace=row.voice_pace,
        tts_voice=row.tts_voice,
        voice_profile=row.tts_voice,
        response_length=row.response_length,
    )
