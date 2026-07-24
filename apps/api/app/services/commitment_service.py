from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Commitment
from .audit_service import record_audit

_CONFIDENCE_THRESHOLD = 0.72
_LOW_CONFIDENCE_THRESHOLD = 0.58
_KNOWN_PROJECT_NAMES = ("Qring", "CampusCart", "FitAccess", "AiPal", "Sammya")
_STRONG_COMMITMENT_PATTERNS = (
    r"\bi\s+(?:will|’ll|'ll)\b",
    r"\bi(?:'m|’m|m)\s+going\s+to\b",
    r"\bi\s+plan\s+to\b",
    r"\bi\s+promised\b",
    r"\bi\s+said\s+i\s+would\b",
    r"\bi\s+said\s+i(?:'d|’d)\b",
    r"\bi\s+committed\s+to\b",
    r"\bi\s+agreed\s+to\b",
)
_AMBIGUOUS_COMMITMENT_PATTERNS = (
    r"\bi\s+need\s+to\b",
    r"\bi\s+should\b",
    r"\bi\s+have\s+to\b",
)
_DUE_HINTS = (
    "tomorrow",
    "day after tomorrow",
    "next week",
    "next month",
    "in ",
    "today",
    "tonight",
    "morning",
    "afternoon",
    "evening",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_NEGATIVE_CONFIDENCE_HINTS = (
    "maybe",
    "might",
    "probably",
    "possibly",
    "if i can",
    "if possible",
    "hopefully",
)
_WEEKDAY_TO_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_MONTH_TO_INDEX = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
_PERSON_CONTEXT_PATTERN = re.compile(
    r"\b(?:promised|told|email|send|sent|call|called|meet|meeting|with|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
)
_PERSON_EXCLUSIONS = {
    "AiPal",
    "Call",
    "CampusCart",
    "FitAccess",
    "Follow",
    "Invoice",
    "Qring",
    "Sammya",
    "Send",
    "Tomorrow",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _looks_like_commitment(text: str) -> bool:
    lower = text.lower()
    if any(re.search(pattern, lower) for pattern in _STRONG_COMMITMENT_PATTERNS):
        return True
    has_due_hint = any(hint in lower for hint in _DUE_HINTS)
    return has_due_hint and any(re.search(pattern, lower) for pattern in _AMBIGUOUS_COMMITMENT_PATTERNS)


def _time_for_hint(text: str) -> tuple[int, int]:
    lower = text.lower()
    if "morning" in lower:
        return 9, 0
    if "afternoon" in lower:
        return 14, 0
    if "evening" in lower:
        return 18, 0
    if "tonight" in lower:
        return 20, 0
    return 9, 0


def _next_weekday(now: datetime, weekday: int, *, force_next: bool = False) -> datetime:
    days_ahead = (weekday - now.weekday()) % 7
    if days_ahead == 0 or force_next:
        days_ahead += 7
    return now + timedelta(days=days_ahead)


def _extract_due_at(text: str) -> datetime | None:
    now = _utcnow()
    lower = text.lower()
    hour, minute = _time_for_hint(text)
    if "day after tomorrow" in lower:
        return (now + timedelta(days=2)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "tomorrow" in lower:
        return (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "next week" in lower:
        return (now + timedelta(days=7)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "next month" in lower:
        return (now + timedelta(days=30)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    relative = re.search(r"\bin\s+(\d{1,2})\s+(day|days|week|weeks)\b", lower)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        days = amount * 7 if unit.startswith("week") else amount
        return (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if "tonight" in lower:
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    if "today" in lower:
        return now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    for day, index in _WEEKDAY_TO_INDEX.items():
        if re.search(rf"\bnext\s+{day}\b", lower):
            return _next_weekday(now, index, force_next=True).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if re.search(rf"\b{day}\b", lower):
            return _next_weekday(now, index).replace(hour=hour, minute=minute, second=0, microsecond=0)
    month_match = re.search(
        r"\b("
        + "|".join(_MONTH_TO_INDEX)
        + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(\d{4}))?\b",
        lower,
    )
    if month_match:
        month = _MONTH_TO_INDEX[month_match.group(1)]
        day = int(month_match.group(2))
        year = int(month_match.group(3) or now.year)
        candidate = datetime(year, month, day, hour, minute, tzinfo=UTC)
        if candidate < now:
            candidate = candidate.replace(year=year + 1)
        return candidate
    return None


def _extract_title(text: str) -> str:
    lowered = _normalize(text)
    lowered = re.sub(r"(?i)^(tomorrow|next week|next month|today|tonight|day after tomorrow)\s+", "", lowered)
    lowered = re.sub(r"(?i)^i\s+(will|’ll|'ll|am going to|m going to|plan to|promised|said i would|said i’d|need to|should|have to|committed to|agreed to)\s+", "", lowered)
    lowered = re.sub(r"(?i)^i\s+", "", lowered)
    lowered = re.sub(r"[.?!]+$", "", lowered).strip()
    if not lowered:
        return "Commitment"
    lowered = lowered[0].upper() + lowered[1:]
    return lowered[:255]


def _confidence_for(text: str) -> float:
    lower = text.lower()
    confidence = 0.52
    if any(re.search(pattern, lower) for pattern in _STRONG_COMMITMENT_PATTERNS):
        confidence += 0.23
    if any(re.search(pattern, lower) for pattern in _AMBIGUOUS_COMMITMENT_PATTERNS):
        confidence += 0.08
    if any(hint in lower for hint in _DUE_HINTS):
        confidence += 0.08
    if any(hint in lower for hint in _NEGATIVE_CONFIDENCE_HINTS):
        confidence -= 0.18
    if len(lower.split()) >= 6:
        confidence += 0.05
    return max(0.0, min(1.0, confidence))


def generate_commitment_followup(commitment: Commitment) -> str:
    title = (commitment.title or "that").strip()
    due_at = _as_aware(commitment.due_at)
    if due_at is not None and due_at < _utcnow():
        return f"You planned to {title.lower()}. Did you get a chance to do that?"
    if due_at is not None:
        return f"You mentioned {title.lower()}. How is that going?"
    return f"Any update on {title.lower()}?" if title else "Any update on that commitment?"


async def _resolve_related_entity(db: AsyncSession, user_id: UUID, text: str) -> tuple[UUID | None, str | None, str | None]:
    try:
        from .knowledge_graph_service import upsert_entity, search_entities
    except Exception:
        return None, None, None

    lower = text.lower()
    chosen = None
    entity_type = None
    for name in _KNOWN_PROJECT_NAMES:
        if name.lower() in lower:
            chosen = name
            entity_type = "project"
            break

    if chosen is None:
        for person_match in _PERSON_CONTEXT_PATTERN.finditer(text):
            candidate = person_match.group(1).strip()
            if candidate not in _PERSON_EXCLUSIONS and candidate.lower() not in {name.lower() for name in _KNOWN_PROJECT_NAMES}:
                chosen = candidate
                break
        if chosen:
            entity_type = "person"

    if chosen is None:
        return None, None, None

    existing = await search_entities(db, user_id, chosen, entity_type=entity_type)
    if existing:
        entity = existing[0]
    else:
        entity = await upsert_entity(
            db,
            user_id,
            entity_type,
            chosen,
            aliases=[chosen.lower()],
            description=f"Linked from commitment: {chosen}",
            confidence=0.82,
            metadata={"source": "commitment"},
        )
    return entity.id, entity.entity_type, entity.name


async def create_commitment(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    content: str,
    due_at: datetime | None = None,
    confidence: float = 0.8,
    source_message_id: UUID | None = None,
    source_memory_id: UUID | None = None,
    follow_up_at: datetime | None = None,
    status: str = "open",
) -> Commitment:
    related_entity_id, related_entity_type, related_entity_name = await _resolve_related_entity(db, user_id, content)
    row = Commitment(
        user_id=user_id,
        title=_normalize(title)[:255],
        content=_normalize(content),
        due_at=due_at,
        status=status,
        source_message_id=source_message_id,
        source_memory_id=source_memory_id,
        follow_up_at=follow_up_at,
        confidence=confidence,
        related_entity_id=related_entity_id,
        related_entity_type=related_entity_type,
        related_entity_name=related_entity_name,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await record_audit(
        db,
        user_id,
        "commitment.create",
        "commitment",
        str(row.id),
        {"title": row.title, "due_at": row.due_at, "confidence": row.confidence},
    )
    from .today_item_service import create_from_commitment

    await create_from_commitment(db, user_id, row)
    return row


def _commitment_is_open(row: Commitment) -> bool:
    return row.status == "open"


async def list_commitments(db: AsyncSession, user_id: UUID) -> list[Commitment]:
    result = await db.execute(
        select(Commitment).where(Commitment.user_id == user_id).order_by(Commitment.created_at.desc())
    )
    return list(result.scalars().all())


async def list_open_commitments(db: AsyncSession, user_id: UUID) -> list[Commitment]:
    result = await db.execute(
        select(Commitment)
        .where(Commitment.user_id == user_id, Commitment.status == "open")
        .order_by(Commitment.due_at.asc().nulls_last(), Commitment.created_at.desc())
    )
    return list(result.scalars().all())


async def list_due_followups(db: AsyncSession, user_id: UUID) -> list[Commitment]:
    now = _utcnow()
    result = await db.execute(
        select(Commitment)
        .where(
            Commitment.user_id == user_id,
            Commitment.status == "open",
            Commitment.follow_up_at.is_not(None),
            Commitment.follow_up_at <= now,
        )
        .order_by(Commitment.follow_up_at.asc(), Commitment.created_at.desc())
    )
    return list(result.scalars().all())


async def get_commitment(db: AsyncSession, user_id: UUID, commitment_id: UUID) -> Commitment | None:
    result = await db.execute(
        select(Commitment).where(Commitment.user_id == user_id, Commitment.id == commitment_id)
    )
    return result.scalar_one_or_none()


async def update_commitment(db: AsyncSession, user_id: UUID, commitment_id: UUID, data: dict) -> Commitment | None:
    row = await get_commitment(db, user_id, commitment_id)
    if row is None:
        return None
    for key in ("title", "content", "due_at", "status", "follow_up_at", "confidence"):
        if key in data and data[key] is not None:
            setattr(row, key, data[key])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    await record_audit(db, user_id, "commitment.update", "commitment", str(row.id), {"status": row.status})
    from .today_item_service import create_from_commitment

    await create_from_commitment(db, user_id, row)
    return row


async def mark_completed(db: AsyncSession, user_id: UUID, commitment_id: UUID) -> Commitment | None:
    row = await update_commitment(db, user_id, commitment_id, {"status": "completed"})
    if row is not None:
        await record_audit(db, user_id, "commitment.complete", "commitment", str(row.id))
    return row


async def dismiss(db: AsyncSession, user_id: UUID, commitment_id: UUID) -> Commitment | None:
    row = await update_commitment(db, user_id, commitment_id, {"status": "dismissed"})
    if row is not None:
        await record_audit(db, user_id, "commitment.dismiss", "commitment", str(row.id))
    return row


def _candidate_from_text(text: str) -> dict[str, object] | None:
    if not text.strip() or not _looks_like_commitment(text):
        return None
    due_at = _extract_due_at(text)
    title = _extract_title(text)
    confidence = _confidence_for(text)
    requires_confirmation = confidence < _CONFIDENCE_THRESHOLD
    follow_up_at = None
    if due_at is not None:
        follow_up_at = due_at + timedelta(days=1)
    else:
        follow_up_at = _utcnow() + timedelta(days=2)
    content = _normalize(text)
    return {
        "title": title,
        "content": content,
        "due_at": due_at,
        "follow_up_at": follow_up_at,
        "confidence": confidence,
        "requires_confirmation": requires_confirmation,
    }


async def extract_commitments(
    db: AsyncSession,
    user_id: UUID,
    message: str,
    source_message_id: UUID | None = None,
    source_memory_id: UUID | None = None,
) -> list[dict[str, object]]:
    candidate = _candidate_from_text(message)
    if candidate is None:
        return []
    if candidate["requires_confirmation"]:
        return [candidate]
    commitment = await create_commitment(
        db,
        user_id,
        title=str(candidate["title"]),
        content=str(candidate["content"]),
        due_at=candidate["due_at"],
        confidence=float(candidate["confidence"]),
        source_message_id=source_message_id,
        source_memory_id=source_memory_id,
        follow_up_at=candidate["follow_up_at"],
    )
    return [
        {
            "id": str(commitment.id),
            "title": commitment.title,
            "content": commitment.content,
            "due_at": _as_aware(commitment.due_at),
            "follow_up_at": _as_aware(commitment.follow_up_at),
            "confidence": float(commitment.confidence or 0.0),
            "requires_confirmation": False,
            "status": commitment.status,
            "related_entity_id": commitment.related_entity_id,
            "related_entity_type": commitment.related_entity_type,
            "related_entity_name": commitment.related_entity_name,
        }
    ]


def commitment_to_dict(commitment: Commitment) -> dict[str, object]:
    return {
        "id": str(commitment.id),
        "user_id": str(commitment.user_id),
        "title": commitment.title,
        "content": commitment.content,
        "due_at": _as_aware(commitment.due_at),
        "status": commitment.status,
        "source_message_id": str(commitment.source_message_id) if commitment.source_message_id else None,
        "source_memory_id": str(commitment.source_memory_id) if commitment.source_memory_id else None,
        "follow_up_at": _as_aware(commitment.follow_up_at),
        "confidence": float(commitment.confidence or 0.0),
        "related_entity_id": str(commitment.related_entity_id) if commitment.related_entity_id else None,
        "related_entity_type": commitment.related_entity_type,
        "related_entity_name": commitment.related_entity_name,
        "created_at": commitment.created_at,
        "updated_at": commitment.updated_at,
    }
