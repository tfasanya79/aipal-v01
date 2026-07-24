from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Memory
from .audit_service import record_audit

_FOLLOWUP_TYPES = {"important_event", "project", "relationship", "person", "win", "failure", "promise", "follow_up"}


def generate_followup_prompt(memory: Memory) -> str:
    title = (memory.title or "that").strip()
    if memory.type == "important_event":
        return memory.follow_up_prompt or f"How did {title} go?"
    if memory.type == "win":
        return memory.follow_up_prompt or f"What happened after {title.lower()}?"
    if memory.type == "failure":
        return memory.follow_up_prompt or f"How are you doing after {title.lower()}?"
    if memory.type == "project":
        return memory.follow_up_prompt or f"How is {title} progressing?"
    if memory.type in {"relationship", "person"}:
        return memory.follow_up_prompt or f"How is {title} going lately?"
    if memory.type == "promise":
        return memory.follow_up_prompt or f"Did you get to {title.lower()}?"
    return memory.follow_up_prompt or f"Any update on {title.lower()}?"


async def list_due_followups(db: AsyncSession, user_id: UUID, *, limit: int = 10) -> list[Memory]:
    now = datetime.now(UTC)
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            Memory.type.in_(list(_FOLLOWUP_TYPES)),
            Memory.paused.is_(False),
            Memory.user_approved.is_(True),
            or_(Memory.follow_up_status.is_(None), Memory.follow_up_status == "pending"),
            Memory.follow_up_at.is_not(None),
            Memory.follow_up_at <= now,
        )
        .order_by(Memory.follow_up_at.asc(), Memory.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_followup_completed(db: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    result = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return None
    memory.follow_up_status = "completed"
    memory.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(memory)
    await record_audit(db, user_id, "memory.followup.complete", "memory", str(memory.id))
    return memory


async def dismiss_followup(db: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    result = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return None
    memory.follow_up_status = "dismissed"
    memory.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(memory)
    await record_audit(db, user_id, "memory.followup.dismiss", "memory", str(memory.id))
    return memory
