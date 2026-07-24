from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..db import get_db
from ..models import Conversation, ConversationTurn, Goal, Reflection, User, Message
from ..schemas import CompanionTurnRequest, CompanionTurnResponse, EmotionResponse, MemoryUsageResponse
from ..conversation.contracts import InputModality
from ..conversation.service import run_conversation
from ..conversation.state import conversation_state_manager
from ..services.companion_home_service import generate_companion_home_brief
from ..services.proactive_conversation_service import get_or_create_preferences
from ..services.goal_service import create_goal, delete_goal, list_active_goals, update_goal
from ..services.memory_service import (
    approve_memory,
    deny_memory,
    delete_memory,
    export_memories,
    list_memories,
    make_memory_permanent,
    make_memory_temporary,
    pending_memories,
    pause_memory,
    reject_memory,
    memory_to_dict,
    search_memories,
    update_memory,
)
from ..services import tasks as task_svc
from ..rate_limit import rate_limit_dependency

router = APIRouter(tags=["companion"], dependencies=[Depends(rate_limit_dependency("companion", limit=60))])


def _uuid_or_none(value):
    if value in (None, ""):
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _dt_or_none(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _normalise_memory_payload(payload: dict) -> dict:
    body = dict(payload)
    if "expires_at" in body:
        body["expires_at"] = _dt_or_none(body.get("expires_at"))
    if "edited_from_id" in body:
        body["edited_from_id"] = _uuid_or_none(body.get("edited_from_id"))
    return body


@router.post("/companion/turn", response_model=CompanionTurnResponse)
async def companion_turn(
    body: CompanionTurnRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await run_conversation(
        db,
        user,
        body.message,
        conversation_id=body.conversation_id,
        modality=InputModality.LIVE_VOICE if body.source == "voice" else InputModality.TEXT,
        source_context=body.source_context,
    )
    preferences = await get_or_create_preferences(db, user.id)
    return CompanionTurnResponse(
        reply=result.reply,
        assistantMessage=result.reply,
        speak=False,
        voiceId=preferences.tts_voice,
        uiState=result.ui_state,
        mode=result.mode,
        emotion=EmotionResponse(**result.emotion),
        memories_used=[MemoryUsageResponse(**m) for m in result.memories_used],
        suggested_actions=result.suggested_actions,
        plan_draft=result.plan_draft,
        requires_confirmation=result.requires_confirmation,
        confirmation_prompt=result.confirmation_prompt,
        conversation_id=result.conversation_id,
    )


@router.get("/companion/home")
async def companion_home(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await generate_companion_home_brief(db, user)


@router.get("/conversations")
async def list_conversations(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.started_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(row.id),
            "mode": row.mode,
            "title": row.title,
            "started_at": row.started_at,
            "ended_at": row.ended_at,
        }
        for row in rows
    ]


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.user_id == user.id, Conversation.id == conversation_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.execute(
        delete(Message).where(Message.user_id == user.id, Message.conversation_id == conversation_id)
    )
    await db.execute(
        delete(ConversationTurn).where(ConversationTurn.user_id == user.id, ConversationTurn.session_id == str(conversation_id))
    )
    await conversation_state_manager.forget(
        db,
        user_id=user.id,
        conversation_id=conversation_id,
    )
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.delete("/conversation-history")
async def clear_conversation_history(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversations = await db.execute(select(Conversation).where(Conversation.user_id == user.id))
    rows = conversations.scalars().all()
    for row in rows:
        await db.execute(delete(Message).where(Message.user_id == user.id, Message.conversation_id == row.id))
        await db.execute(
            delete(ConversationTurn).where(
                ConversationTurn.user_id == user.id,
                ConversationTurn.session_id == str(row.id),
            )
        )
        await conversation_state_manager.forget(
            db,
            user_id=user.id,
            conversation_id=row.id,
        )
        await db.delete(row)
    await db.commit()
    return {"ok": True, "deleted": len(rows)}


@router.get("/memory")
async def list_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await list_memories(db, user.id)
    return [memory_to_dict(row) for row in rows]


@router.get("/memory/pending")
async def list_pending_memory(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = await pending_memories(db, user.id)
    return [memory_to_dict(row) for row in rows]


@router.post("/memory")
async def create_memory_route(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from ..services.memory_service import create_memory

    user_approved = bool(payload.get("user_approved", True))
    sensitive = bool(payload.get("sensitive", False))

    memory = await create_memory(
        db,
        user.id,
        type=payload.get("type", "fact"),
        life_area=payload.get("life_area"),
        title=payload.get("title", "Memory"),
        content=payload.get("content", ""),
        importance=int(payload.get("importance", 1)),
        confidence=float(payload.get("confidence", 0.5)),
        follow_up_at=_dt_or_none(payload.get("follow_up_at")),
        follow_up_status=payload.get("follow_up_status"),
        follow_up_prompt=payload.get("follow_up_prompt"),
        event_date=_dt_or_none(payload.get("event_date")),
        entities=payload.get("entities"),
        sentiment=payload.get("sentiment"),
        approval_status=payload.get("approval_status") or ("pending" if sensitive or not user_approved else "approved"),
        memory_scope=payload.get("memory_scope", "permanent"),
        expires_at=_dt_or_none(payload.get("expires_at")),
        suggested_reason=payload.get("suggested_reason"),
        edited_from_id=_uuid_or_none(payload.get("edited_from_id")),
        sensitive=sensitive,
        user_approved=user_approved,
    )
    return {"id": str(memory.id)}


@router.patch("/memory/{memory_id}")
async def patch_memory(
    memory_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await update_memory(db, user.id, memory_id, _normalise_memory_payload(payload))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.patch("/memory/{memory_id}/edit")
async def edit_memory(
    memory_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await update_memory(db, user.id, memory_id, _normalise_memory_payload(payload))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.delete("/memory/{memory_id}")
async def remove_memory(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_memory(db, user.id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/pause")
async def pause_memory_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await pause_memory(db, user.id, memory_id, paused=True)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/resume")
async def resume_memory_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await pause_memory(db, user.id, memory_id, paused=False)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/approve")
async def approve_memory_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await approve_memory(db, user.id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.post("/memory/{memory_id}/deny")
async def deny_memory_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await deny_memory(db, user.id, memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.post("/memory/{memory_id}/reject")
async def reject_memory_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await reject_memory(db, user.id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.post("/memory/{memory_id}/make-temporary")
async def make_memory_temporary_route(
    memory_id: UUID,
    payload: dict | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await make_memory_temporary(db, user.id, memory_id, expires_at=_dt_or_none((payload or {}).get("expires_at")))
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.post("/memory/{memory_id}/make-permanent")
async def make_memory_permanent_route(
    memory_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await make_memory_permanent(db, user.id, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": memory_to_dict(memory)}


@router.post("/memory/search")
async def search_memory_route(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memories = await search_memories(db, user.id, payload.get("query", ""), limit=int(payload.get("limit", 8)))
    return [
        {
            "id": str(m.id),
            "title": m.title,
            "type": m.type,
            "life_area": m.life_area,
            "content": m.content,
        }
        for m in memories
    ]


@router.get("/memory/export")
async def export_memory_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await export_memories(db, user.id)


@router.get("/goals")
async def list_goals_route(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goals = await list_active_goals(db, user.id)
    return [
        {
            "id": str(goal.id),
            "title": goal.title,
            "description": goal.description,
            "life_area": goal.life_area,
            "status": goal.status,
            "priority": goal.priority,
            "target_date": goal.target_date,
        }
        for goal in goals
    ]


@router.post("/goals")
async def create_goal_route(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await create_goal(db, user.id, payload)
    return {"id": str(goal.id)}


@router.patch("/goals/{goal_id}")
async def patch_goal_route(
    goal_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    goal = await update_goal(db, user.id, goal_id, payload)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


@router.delete("/goals/{goal_id}")
async def delete_goal_route(
    goal_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_goal(db, user.id, goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"ok": True}


@router.get("/goals/{goal_id}")
async def get_goal_route(
    goal_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Goal).where(Goal.user_id == user.id, Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return {
        "id": str(goal.id),
        "title": goal.title,
        "description": goal.description,
        "life_area": goal.life_area,
        "status": goal.status,
        "priority": goal.priority,
        "target_date": goal.target_date,
    }


@router.get("/goals/{goal_id}/detail")
async def get_goal_detail_route(
    goal_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Goal).where(Goal.user_id == user.id, Goal.id == goal_id))
    goal = result.scalar_one_or_none()
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    linked_tasks = await task_svc.list_tasks(db, user.id, goal_id=goal_id, top_level_only=False)
    linked_reflections_result = await db.execute(
        select(Reflection).where(Reflection.user_id == user.id, Reflection.goal_id == goal_id).order_by(Reflection.created_at.desc())
    )
    linked_reflections = linked_reflections_result.scalars().all()
    return {
        "goal": {
            "id": str(goal.id),
            "title": goal.title,
            "description": goal.description,
            "life_area": goal.life_area,
            "status": goal.status,
            "priority": goal.priority,
            "target_date": goal.target_date,
            "created_at": goal.created_at,
            "updated_at": goal.updated_at,
        },
        "linked_tasks": [
            {
                "id": task.id,
                "title": task.title,
                "notes": task.notes,
                "due_at": task.due_at,
                "priority": task.priority,
                "status": task.status,
                "source": task.source,
                "goal_id": task.goal_id,
                "parent_task_id": task.parent_task_id,
                "estimated_minutes": task.estimated_minutes,
                "sort_order": task.sort_order,
                "category": task.category,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
            }
            for task in linked_tasks
        ],
        "linked_reflections": [
            {
                "id": str(r.id),
                "type": r.type,
                "wins": r.wins,
                "challenges": r.challenges,
                "lessons": r.lessons,
                "mood": r.mood,
                "goal_id": r.goal_id,
                "created_at": r.created_at,
            }
            for r in linked_reflections
        ],
    }


@router.get("/reflections")
async def list_reflections_route(
    goal_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    q = select(Reflection).where(Reflection.user_id == user.id)
    if goal_id is not None:
        q = q.where(Reflection.goal_id == goal_id)
    result = await db.execute(q.order_by(Reflection.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "type": r.type,
            "wins": r.wins,
            "challenges": r.challenges,
            "lessons": r.lessons,
            "mood": r.mood,
            "goal_id": r.goal_id,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.get("/reflections/{reflection_id}/detail")
async def get_reflection_detail_route(
    reflection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reflection).where(Reflection.user_id == user.id, Reflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if reflection is None:
        raise HTTPException(status_code=404, detail="Reflection not found")
    linked_goal = None
    if reflection.goal_id is not None:
        goal_result = await db.execute(
            select(Goal).where(Goal.user_id == user.id, Goal.id == reflection.goal_id)
        )
        goal = goal_result.scalar_one_or_none()
        if goal is not None:
            linked_goal = {
                "id": str(goal.id),
                "title": goal.title,
                "description": goal.description,
                "life_area": goal.life_area,
                "status": goal.status,
                "priority": goal.priority,
                "target_date": goal.target_date,
                "created_at": goal.created_at,
                "updated_at": goal.updated_at,
            }
    return {
        "reflection": {
            "id": str(reflection.id),
            "type": reflection.type,
            "wins": reflection.wins,
            "challenges": reflection.challenges,
            "lessons": reflection.lessons,
            "mood": reflection.mood,
            "goal_id": reflection.goal_id,
            "created_at": reflection.created_at,
        },
        "linked_goal": linked_goal,
    }


@router.post("/reflections")
async def create_reflection(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reflection = Reflection(
        user_id=user.id,
        goal_id=_uuid_or_none(payload.get("goal_id")),
        type=payload.get("type", "daily"),
        wins=payload.get("wins"),
        challenges=payload.get("challenges"),
        lessons=payload.get("lessons"),
        mood=payload.get("mood"),
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return {"id": str(reflection.id)}


@router.patch("/reflections/{reflection_id}")
async def update_reflection(
    reflection_id: UUID,
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reflection).where(Reflection.user_id == user.id, Reflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if reflection is None:
        raise HTTPException(status_code=404, detail="Reflection not found")
    for key in ("type", "wins", "challenges", "lessons", "mood", "goal_id"):
        if key in payload:
            value = payload[key]
            if key == "goal_id" and value == "":
                value = None
            if key == "goal_id" and value is not None:
                value = _uuid_or_none(value)
            if value is not None:
                setattr(reflection, key, value)
    await db.commit()
    await db.refresh(reflection)
    return {"ok": True}


@router.delete("/reflections/{reflection_id}")
async def delete_reflection(
    reflection_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Reflection).where(Reflection.user_id == user.id, Reflection.id == reflection_id)
    )
    reflection = result.scalar_one_or_none()
    if reflection is None:
        raise HTTPException(status_code=404, detail="Reflection not found")
    await db.delete(reflection)
    await db.commit()
    return {"ok": True}


@router.post("/reflections/daily")
async def create_daily_reflection(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reflection = Reflection(
        user_id=user.id,
        goal_id=_uuid_or_none(payload.get("goal_id")),
        type="daily",
        wins=payload.get("wins"),
        challenges=payload.get("challenges"),
        lessons=payload.get("lessons"),
        mood=payload.get("mood"),
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return {"id": str(reflection.id)}


@router.post("/reflections/weekly")
async def create_weekly_reflection(
    payload: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    reflection = Reflection(
        user_id=user.id,
        goal_id=_uuid_or_none(payload.get("goal_id")),
        type="weekly",
        wins=payload.get("wins"),
        challenges=payload.get("challenges"),
        lessons=payload.get("lessons"),
        mood=payload.get("mood"),
    )
    db.add(reflection)
    await db.commit()
    await db.refresh(reflection)
    return {"id": str(reflection.id)}
