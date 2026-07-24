import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConversationTurn

MAX_TURNS = 12


async def append_turn(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    role: str,
    content: str,
) -> None:
    db.add(
        ConversationTurn(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
        )
    )
    await db.commit()


async def load_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
    limit: int = MAX_TURNS,
) -> list[dict[str, str]]:
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.user_id == user_id, ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.created_at.desc())
        .limit(limit)
    )
    turns = list(reversed(result.scalars().all()))
    return [{"role": t.role, "content": t.content} for t in turns]


async def list_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 12,
) -> list[dict[str, object]]:
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.user_id == user_id)
        .order_by(ConversationTurn.created_at.desc())
    )
    sessions: dict[str, dict[str, object]] = {}
    for turn in result.scalars().all():
        item = sessions.get(turn.session_id)
        if item is None:
            item = {
                "session_id": turn.session_id,
                "preview": turn.content[:140],
                "last_role": turn.role,
                "last_activity_at": turn.created_at,
                "turn_count": 0,
            }
            sessions[turn.session_id] = item
        item["turn_count"] = int(item["turn_count"]) + 1
        if turn.role == "user" and str(item["preview"]).startswith("AiPal replied:"):
            item["preview"] = turn.content[:140]
        if turn.created_at > item["last_activity_at"]:  # type: ignore[operator]
            item["last_activity_at"] = turn.created_at
            item["last_role"] = turn.role
            if turn.role == "user":
                item["preview"] = turn.content[:140]
    ordered = sorted(
        sessions.values(),
        key=lambda item: item["last_activity_at"],
        reverse=True,
    )
    return ordered[:limit]


async def get_session_turns(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
) -> list[dict[str, object]]:
    result = await db.execute(
        select(ConversationTurn)
        .where(
            ConversationTurn.user_id == user_id,
            ConversationTurn.session_id == session_id,
        )
        .order_by(ConversationTurn.created_at.asc())
    )
    return [
        {
            "id": t.id,
            "role": t.role,
            "content": t.content,
            "created_at": t.created_at,
        }
        for t in result.scalars().all()
    ]


async def delete_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: str,
) -> int:
    result = await db.execute(
        select(ConversationTurn).where(
            ConversationTurn.user_id == user_id,
            ConversationTurn.session_id == session_id,
        )
    )
    turns = result.scalars().all()
    for turn in turns:
        await db.delete(turn)
    await db.commit()
    return len(turns)


async def has_chatted_today(
    db: AsyncSession,
    user_id: uuid.UUID,
    timezone: str | None = None,
) -> bool:
    from datetime import UTC, datetime, time
    from zoneinfo import ZoneInfo

    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_day = datetime.now(tz).date()
    start = datetime.combine(local_day, time.min, tzinfo=tz).astimezone(UTC)
    result = await db.execute(
        select(ConversationTurn.id)
        .where(ConversationTurn.user_id == user_id, ConversationTurn.created_at >= start)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
