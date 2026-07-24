from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Memory, ProactivePrompt, UserCompanionPreference
from .memory_service import recent_life_area_insight
from .relationship_followup_service import list_due_followups, generate_followup_prompt
from .goal_service import list_active_goals


def _parse_hhmm(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        hour, minute = value.split(":")
        return max(0, min(23, int(hour))), max(0, min(59, int(minute)))
    except Exception:
        return None


async def get_or_create_preferences(db: AsyncSession, user_id: UUID) -> UserCompanionPreference:
    result = await db.execute(select(UserCompanionPreference).where(UserCompanionPreference.user_id == user_id))
    row = result.scalar_one_or_none()
    if row is not None:
        return row
    row = UserCompanionPreference(user_id=user_id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_preferences(db: AsyncSession, user_id: UUID, data: dict) -> UserCompanionPreference:
    row = await get_or_create_preferences(db, user_id)
    if data.get("voice_profile") and not data.get("tts_voice"):
        data["tts_voice"] = data["voice_profile"]
    for key in (
        "proactive_enabled",
        "max_proactive_per_day",
        "quiet_hours_start",
        "quiet_hours_end",
        "tone",
        "humor_level",
        "directness_level",
        "voice_pace",
        "tts_voice",
        "response_length",
    ):
        if key in data and data[key] is not None:
            setattr(row, key, data[key])
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


async def list_proactive_prompts(db: AsyncSession, user_id: UUID, status: str | None = None) -> list[ProactivePrompt]:
    stmt = select(ProactivePrompt).where(ProactivePrompt.user_id == user_id).order_by(ProactivePrompt.created_at.desc())
    if status:
        stmt = stmt.where(ProactivePrompt.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _prompt_count_today(db: AsyncSession, user_id: UUID) -> int:
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    result = await db.execute(
        select(func.count()).select_from(ProactivePrompt).where(
            ProactivePrompt.user_id == user_id,
            ProactivePrompt.delivered_at.is_not(None),
            ProactivePrompt.delivered_at >= start,
            ProactivePrompt.delivered_at < end,
        )
    )
    return int(result.scalar_one() or 0)


async def _quiet_hours_blocked(pref: UserCompanionPreference) -> bool:
    now = datetime.now(UTC)
    start = _parse_hhmm(pref.quiet_hours_start)
    end = _parse_hhmm(pref.quiet_hours_end)
    if not start or not end:
        return False
    current = now.hour * 60 + now.minute
    start_minutes = start[0] * 60 + start[1]
    end_minutes = end[0] * 60 + end[1]
    if start_minutes <= end_minutes:
        return start_minutes <= current <= end_minutes
    return current >= start_minutes or current <= end_minutes


async def _recent_meaningful_memory_prompt(db: AsyncSession, user_id: UUID) -> tuple[str, str, UUID | None] | None:
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=14)
    cool_off = now - timedelta(hours=2)
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.paused.is_(False),
            Memory.user_approved.is_(True),
            Memory.created_at >= cutoff,
            Memory.created_at <= cool_off,
            Memory.type.in_(
                [
                    "important_event",
                    "win",
                    "failure",
                    "recurring_concern",
                    "emotional_pattern",
                    "project",
                    "relationship",
                    "person",
                ]
            ),
        ).order_by(Memory.importance.desc(), Memory.created_at.desc()).limit(12)
    )
    for memory in result.scalars().all():
        title = (memory.title or memory.content or "that").strip().rstrip(".")
        if not title:
            continue
        if memory.type == "important_event":
            prompt = memory.follow_up_prompt or f"You mentioned {title}. How did it go?"
        elif memory.type == "win":
            prompt = f"You mentioned {title}. What helped make that happen?"
        elif memory.type == "failure":
            prompt = memory.follow_up_prompt or f"You mentioned {title}. How are you doing with that now?"
        elif memory.type in {"recurring_concern", "emotional_pattern"}:
            prompt = memory.follow_up_prompt or f"You mentioned {title}. Want to unpack it a little?"
        elif memory.type in {"project", "relationship", "person"}:
            prompt = memory.follow_up_prompt or f"How is {title} going lately?"
        else:
            continue
        return prompt, "memory", memory.id
    return None


async def generate_proactive_prompt(db: AsyncSession, user_id: UUID, force: bool = False) -> ProactivePrompt | None:
    pref = await get_or_create_preferences(db, user_id)
    if not pref.proactive_enabled and not force:
        return None
    if await _quiet_hours_blocked(pref) and not force:
        return None
    if not force and await _prompt_count_today(db, user_id) >= max(pref.max_proactive_per_day, 1):
        return None

    due_followups = await list_due_followups(db, user_id, limit=3)
    if due_followups:
        memory = due_followups[0]
        prompt = generate_followup_prompt(memory)
        trigger_type = "followup"
        source_type = "memory"
        source_id = memory.id
    else:
        recent_prompt = await _recent_meaningful_memory_prompt(db, user_id)
        if recent_prompt is not None:
            prompt, trigger_type, source_id = recent_prompt
            source_type = "memory"
        else:
            life_area = await recent_life_area_insight(db, user_id)
            if life_area is not None:
                prompt = str(life_area["text"])
                trigger_type = "life_area"
                source_type = "life_area"
                source_id = None
            else:
                goals = await list_active_goals(db, user_id)
                if goals:
                    prompt = f"You mentioned {goals[0].title}. Want to check in on that?"
                    trigger_type = "goal"
                    source_type = "goal"
                    source_id = goals[0].id
                else:
                    result = await db.execute(
                        select(Memory).where(
                            Memory.user_id == user_id,
                            Memory.paused.is_(False),
                            Memory.user_approved.is_(True),
                        ).order_by(Memory.created_at.desc()).limit(1)
                    )
                    memory = result.scalar_one_or_none()
                    if memory is None:
                        return None
                    prompt = memory.follow_up_prompt or f"How has {memory.title.lower()} been going?"
                    trigger_type = "memory"
                    source_type = "memory"
                    source_id = memory.id

    structured_context = {
        "trigger_type": trigger_type,
        "source_type": source_type,
        "source_id": str(source_id) if source_id else None,
        "suggested_intent": "gentle_check_in",
        "context": prompt,
    }
    row = ProactivePrompt(
        user_id=user_id,
        trigger_type=trigger_type,
        prompt="Structured proactive trigger ready.",
        trigger_metadata=structured_context,
        source_type=source_type,
        source_id=source_id,
        status="pending",
        priority=5,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def mark_proactive_delivered(db: AsyncSession, user_id: UUID, prompt_id: UUID) -> ProactivePrompt | None:
    result = await db.execute(select(ProactivePrompt).where(ProactivePrompt.user_id == user_id, ProactivePrompt.id == prompt_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = "delivered"
    row.delivered_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row


async def dismiss_proactive(db: AsyncSession, user_id: UUID, prompt_id: UUID) -> ProactivePrompt | None:
    result = await db.execute(select(ProactivePrompt).where(ProactivePrompt.user_id == user_id, ProactivePrompt.id == prompt_id))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.status = "dismissed"
    row.dismissed_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(row)
    return row
