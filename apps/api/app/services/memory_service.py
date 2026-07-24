from __future__ import annotations

import re
from collections import defaultdict
import asyncio
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from collections import Counter
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db import async_session
from ..models import Conversation, Message, Memory
from .audit_service import record_audit
from .embedding_service import cosine_similarity, embed_text
from .business_context_service import create_event, match_project_for_text

_SENSITIVE_WORDS = (
    "medication",
    "diagnosis",
    "diagnosed",
    "therapy",
    "ssn",
    "password",
    "bank",
    "credit card",
    "relationship",
    "pregnant",
    "health",
    "diabetes",
    "sick",
    "depressed",
    "suicidal",
)

_LIFE_AREA_HINTS = {
    "business": ("business", "customer", "client", "sales", "buying", "sell", "launch", "product", "company", "startup", "marketing", "demo", "pitch", "investor", "qring", "estate"),
    "health": ("workout", "gym", "sleep", "tired", "exhausted", "doctor", "health", "medication", "diet", "exercise", "burned out", "burnt out"),
    "finance": ("money", "budget", "bank", "invoice", "payment", "tax", "expense", "income", "revenue", "salary", "investment"),
    "relationships": ("wife", "husband", "partner", "friend", "family", "mom", "dad", "relationship", "mentor", "spouse", "marriage"),
    "learning": ("study", "learn", "course", "book", "practice", "lesson", "train", "read", "reading"),
    "spiritual": ("prayer", "praying", "prayed", "spiritual", "church", "faith", "god", "meditate", "bible", "worship"),
    "personal": ("my day", "myself", "stress", "drained", "emotionally drained", "routine", "life", "home", "wellbeing", "well-being", "mental", "confidence", "discipline", "growth", "overwhelmed"),
}

_LIFE_AREA_PRIORITY = ("business", "health", "finance", "relationships", "learning", "spiritual", "personal")

_LIFE_AREA_NUDGES = {
    "business": "You've talked a lot about business recently. How have you been taking care of yourself?",
    "health": "You've talked a lot about health recently. How are you feeling day to day?",
    "finance": "You've talked a lot about finance recently. Do you feel steady or stressed there?",
    "relationships": "You've talked a lot about relationships recently. How are the people around you doing?",
    "learning": "You've talked a lot about learning recently. What are you hoping to build next?",
    "spiritual": "You've talked a lot about spirituality recently. How is that feeling for you lately?",
    "personal": "You've been circling a few personal themes lately. What feels most important right now?",
}

_RELATIONSHIP_MEMORY_TYPES = {
    "project",
    "relationship",
    "person",
    "recurring_concern",
    "important_event",
    "win",
    "failure",
    "decision",
    "milestone",
    "promise",
    "follow_up",
    "emotional_pattern",
}

_FOLLOW_UP_TYPES = {"important_event", "project", "relationship", "person", "win", "failure", "promise", "follow_up"}

_POSITIVE_WORDS = (
    "won",
    "win",
    "closed",
    "completed",
    "finished",
    "shipped",
    "launched",
    "signed",
    "progress",
    "improved",
    "better",
    "success",
    "helped",
)

_NEGATIVE_WORDS = (
    "nobody",
    "not buying",
    "failed",
    "failure",
    "lost",
    "stuck",
    "blocked",
    "worried",
    "concern",
    "frustrated",
    "angry",
    "sad",
    "tired",
    "drained",
)

_EVENT_WORDS = ("tomorrow", "next week", "next month", "demo", "meeting", "call", "presentation", "launch", "deadline", "interview", "trip", "birthday")
_PROJECT_WORDS = ("project", "launch", "build", "ship", "demo", "client", "customer", "pipeline", "website", "app", "qring")
_PROMISE_WORDS = ("will", "promise", "remind", "follow up", "circle back", "check in")
_CONCERN_WORDS = ("nobody", "not buying", "worried", "concern", "stress", "stuck", "blocked", "struggling", "frustrated")
_WIN_WORDS = ("closed", "won", "landed", "booked", "signed", "shipped", "launched", "finished", "completed")
_FAILURE_WORDS = ("failed", "lost", "missed", "broke", "couldn't", "cannot", "can’t", "didn't", "did not")
_RELATIONSHIP_WORDS = ("wife", "husband", "partner", "friend", "family", "mom", "dad", "brother", "sister", "daughter", "son", "relationship", "girlfriend", "boyfriend", "coworker", "client")
_SEMANTIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "but",
    "did",
    "didnt",
    "do",
    "does",
    "for",
    "from",
    "have",
    "having",
    "i",
    "im",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "this",
    "to",
    "was",
    "we",
    "were",
    "with",
    "you",
    "your",
}
_AUTO_SAVE_CONFIDENCE_THRESHOLD = 0.78
_LIFE_AREA_CONFIDENCE_THRESHOLD = 0.58
_TEMPORARY_MEMORY_DEFAULT_DAYS = 7
_SETTINGS = get_settings()


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _as_utc(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.now(UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _memory_is_expired(memory: Memory, now: datetime | None = None) -> bool:
    if memory.approval_status == "expired":
        return True
    if memory.memory_scope != "temporary" or memory.expires_at is None:
        return False
    return _as_utc(memory.expires_at) <= _as_utc(now or datetime.now(UTC))


def _memory_is_visible(memory: Memory, now: datetime | None = None, *, include_pending: bool = True) -> bool:
    if memory.paused:
        return False
    if memory.approval_status == "rejected":
        return False
    if _memory_is_expired(memory, now):
        return False
    if not include_pending and memory.approval_status != "approved":
        return False
    return True


def _memory_visibility_condition(*, include_pending: bool = True):
    now = datetime.now(UTC)
    state_condition = (
        or_(Memory.approval_status == "approved", Memory.approval_status == "pending")
        if include_pending
        else Memory.approval_status == "approved"
    )
    return and_(
        Memory.paused.is_(False),
        Memory.approval_status != "rejected",
        state_condition,
        or_(Memory.memory_scope != "temporary", Memory.expires_at.is_(None), Memory.expires_at > now),
    )


def _tokenize(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) > 2}


def _classify_life_area(text: str) -> tuple[str | None, float]:
    lower = text.lower()
    scores: dict[str, float] = {}
    for area, hints in _LIFE_AREA_HINTS.items():
        score = 0.0
        for hint in hints:
            if hint in lower:
                score += 1.0
                if " " in hint:
                    score += 0.35
        scores[area] = score
    best_area = max(_LIFE_AREA_PRIORITY, key=lambda area: (scores.get(area, 0.0), -_LIFE_AREA_PRIORITY.index(area)))
    best_score = scores.get(best_area, 0.0)
    if best_score <= 0:
        return None, 0.0
    sorted_scores = sorted(scores.values(), reverse=True)
    second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
    confidence = min(1.0, 0.42 + (best_score * 0.14) + max(best_score - second_score, 0.0) * 0.12)
    if confidence < _LIFE_AREA_CONFIDENCE_THRESHOLD:
        return None, confidence
    return best_area, confidence


def _life_area_for(text: str) -> str | None:
    area, _confidence = _classify_life_area(text)
    return area


def _life_area_nudge(area: str | None) -> str | None:
    if not area:
        return None
    return _LIFE_AREA_NUDGES.get(area.lower())


def _sentiment_for(text: str) -> str:
    lower = text.lower()
    positive = sum(1 for word in _POSITIVE_WORDS if word in lower)
    negative = sum(1 for word in _NEGATIVE_WORDS if word in lower)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _extract_entities(text: str) -> list[str]:
    entities: list[str] = []
    for match in re.findall(r"\b[A-Z][a-zA-Z0-9&'-]{1,}\b", text):
        lowered = match.lower()
        if lowered in {"i", "ai", "april", "today", "tomorrow", "my", "me", "mine", "you", "your"} or lowered.endswith(("'m", "'re", "'ve", "'d", "'ll", "n't")):
            continue
        if match not in entities:
            entities.append(match)
    quoted = re.findall(r'"([^"]{2,80})"|\'([^\']{2,80})\'', text)
    for first, second in quoted:
        entity = first or second
        if entity and entity not in entities:
            entities.append(entity)
    return entities[:6]


def _normalise_entity_values(value: dict | list | str | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip().lower()} if value.strip() else set()
    if isinstance(value, dict):
        collected: set[str] = set()
        for key, item in value.items():
            collected.update(_normalise_entity_values(key))
            collected.update(_normalise_entity_values(item))
        return collected
    collected = set()
    for item in value:
        if isinstance(item, dict):
            collected.update(_normalise_entity_values(item))
        elif item is not None:
            text = str(item).strip().lower()
            if text:
                collected.add(text)
    return collected


def _semantic_tokens(text: str) -> set[str]:
    return {token for token in _tokenize(text) if token not in _SEMANTIC_STOPWORDS}


def _semantic_overlap(left: str, right: str) -> float:
    left_tokens = _semantic_tokens(left)
    right_tokens = _semantic_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    shared = len(left_tokens & right_tokens)
    if shared == 0:
        return 0.0
    return shared / max(min(len(left_tokens), len(right_tokens)), 1)


def _confidence_for_candidate(memory_type: str, text: str, title: str, entities: list[str], life_area: str | None) -> float:
    lower = text.lower()
    confidence = {
        "important_event": 0.84,
        "recurring_concern": 0.88,
        "win": 0.9,
        "failure": 0.87,
        "project": 0.8,
        "relationship": 0.82,
        "person": 0.77,
        "promise": 0.73,
        "follow_up": 0.72,
        "decision": 0.67,
        "milestone": 0.76,
        "emotional_pattern": 0.81,
        "fact": 0.56,
        "goal": 0.6,
        "preference": 0.58,
        "emotion": 0.62,
        "habit": 0.6,
        "reflection": 0.66,
        "challenge": 0.7,
    }.get(memory_type, 0.58)
    word_count = len(text.split())
    if word_count >= 8:
        confidence += 0.06
    elif word_count <= 4:
        confidence -= 0.08
    if entities:
        confidence += 0.04
    if life_area:
        confidence += 0.03
    if title and title.lower() not in lower:
        confidence += 0.02
    if memory_type in {"relationship", "person"} and not entities:
        confidence -= 0.12
    if memory_type == "important_event" and not entities:
        confidence -= 0.07
    if memory_type == "project" and "demo" in lower and "qring" not in lower:
        confidence -= 0.08
    if memory_type == "important_event" and not any(word in lower for word in ("tomorrow", "next week", "next month", "today", "meeting", "demo", "launch", "deadline")):
        confidence -= 0.05
    if memory_type == "recurring_concern" and not any(word in lower for word in ("nobody", "not buying", "frustrat", "stuck", "blocked", "worried", "struggl")):
        confidence -= 0.05
    return max(0.0, min(1.0, round(confidence, 2)))


def _suggested_reason_for_candidate(memory_type: str, confidence: float, sensitive: bool) -> str | None:
    if sensitive:
        return "Sensitive memory needs your review before it is saved."
    if confidence < _AUTO_SAVE_CONFIDENCE_THRESHOLD:
        return f"Low confidence ({confidence:.2f}); this may need your confirmation."
    if memory_type == "important_event":
        return "This looks like an important event worth remembering."
    if memory_type == "recurring_concern":
        return "This sounds like a recurring concern worth tracking."
    if memory_type in {"win", "failure", "decision", "milestone"}:
        return "This looks like a meaningful long-term memory."
    return None


def _derive_title(memory_type: str, text: str, entities: list[str]) -> str:
    stripped = _normalise(text)
    lower = stripped.lower()
    if memory_type == "important_event":
        if entities and any(token.lower() == "qring" for token in entities):
            if "demo" in lower:
                return "Qring demo"
        if "demo" in lower:
            return "Demo"
        if "meeting" in lower:
            return "Meeting"
        if "launch" in lower:
            return "Launch"
    if memory_type == "recurring_concern":
        if "sales" in lower or "buying" in lower:
            return "Concern about sales"
        return "Recurring concern"
    if memory_type == "win":
        if "customer" in lower and "closed" in lower:
            return "Closed customer"
        return stripped[:64].rstrip(" ,.")
    if memory_type == "failure":
        return stripped[:64].rstrip(" ,.")
    if memory_type in {"relationship", "person"}:
        if entities:
            return entities[0]
        return stripped[:64].rstrip(" ,.")
    if memory_type == "project":
        if "qring" in lower:
            return "Qring project"
        if "launch" in lower:
            return "Launch project"
        return stripped[:64].rstrip(" ,.")
    if memory_type == "promise":
        return "Promise"
    if memory_type == "follow_up":
        return "Follow-up"
    if memory_type == "milestone":
        return "Milestone"
    if memory_type == "decision":
        return "Decision"
    if memory_type == "emotional_pattern":
        return "Emotional pattern"
    return stripped[:64].rstrip(" ,.")


def _looks_like_event(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _EVENT_WORDS)


def _looks_like_project(text: str) -> bool:
    lower = text.lower()
    if "qring" in lower and "demo" in lower:
        return True
    return any(word in lower for word in ("project", "startup", "app", "website", "pipeline", "product", "build", "ship", "launch")) or (
        "client" in lower and "project" in lower
    )


def _looks_like_concern(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _CONCERN_WORDS)


def _looks_like_win(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _WIN_WORDS)


def _looks_like_failure(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _FAILURE_WORDS)


def _looks_like_relationship(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _RELATIONSHIP_WORDS) or bool(
        re.search(r"\b(with|to|from|met|called|texted|talked to|spoke with)\s+[A-Z][a-z]+", text)
    )


def _looks_like_promise(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _PROMISE_WORDS)


def _followup_delta(text: str, *, default_days: int = 3) -> timedelta:
    lower = text.lower()
    if "tomorrow" in lower:
        return timedelta(days=1)
    if "next week" in lower:
        return timedelta(days=7)
    if "next month" in lower:
        return timedelta(days=30)
    return timedelta(days=default_days)


def _extract_event_date(text: str) -> datetime | None:
    lower = text.lower()
    now = datetime.now(UTC)
    if "tomorrow" in lower:
        return now + timedelta(days=1)
    if "next week" in lower:
        return now + timedelta(days=7)
    if "next month" in lower:
        return now + timedelta(days=30)
    if "today" in lower:
        return now
    return None


def _similar_text(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a).lower(), _normalise(b).lower()).ratio()


async def _is_duplicate_candidate(db: AsyncSession, user_id: UUID, candidate: dict) -> bool:
    result = await db.execute(
        select(Memory.title, Memory.content, Memory.type, Memory.created_at, Memory.entities)
        .where(
            Memory.user_id == user_id,
            Memory.type == candidate["type"],
            Memory.created_at >= datetime.now(UTC) - timedelta(days=21),
        )
        .order_by(Memory.created_at.desc())
        .limit(25)
    )
    candidate_text = f"{candidate['title']} {candidate['content']}".strip()
    candidate_embedding = embed_text(candidate_text)
    candidate_entities = _normalise_entity_values(candidate.get("entities"))
    for title, content, _type, created_at, entities in result.all():
        existing_text = f"{title or ''} {content or ''}".strip()
        existing_embedding = embed_text(existing_text)
        existing_entities = _normalise_entity_values(entities)
        if title and candidate["title"] and _similar_text(str(title), candidate["title"]) >= 0.84:
            return True
        if content and candidate["content"] and _similar_text(str(content), candidate["content"]) >= 0.88:
            return True
        if title and content and _similar_text(existing_text, candidate_text) >= 0.83:
            return True
        if candidate_entities and existing_entities and candidate_entities & existing_entities:
            if _semantic_overlap(existing_text, candidate_text) >= 0.48:
                return True
        if cosine_similarity(existing_embedding, candidate_embedding) >= 0.9:
            return True
        if _semantic_overlap(existing_text, candidate_text) >= 0.76:
            return True
    return False


def _build_candidate(
    memory_type: str,
    text: str,
    *,
    emotion: str | None = None,
    mode: str | None = None,
) -> dict[str, object] | None:
    if not text or _is_trivial(text):
        return None
    sentiment = _sentiment_for(text)
    event_date = _extract_event_date(text)
    entities = _extract_entities(text)
    life_area, life_area_confidence = _classify_life_area(text)
    sensitive = _is_sensitive(text)
    title = _derive_title(memory_type, text, entities)
    importance = 2
    follow_up_at = None
    follow_up_prompt = None

    if memory_type == "important_event":
        importance = 8
        follow_up_at = (event_date + timedelta(days=1)) if event_date else datetime.now(UTC) + timedelta(days=2)
        follow_up_prompt = f"How did {title} go?"
    elif memory_type == "recurring_concern":
        importance = 7
        follow_up_at = datetime.now(UTC) + timedelta(days=7)
        follow_up_prompt = f"Has anything changed about {title.lower()}?"
    elif memory_type == "win":
        importance = 9
        follow_up_at = datetime.now(UTC) + timedelta(days=3)
        follow_up_prompt = f"What happened after {title.lower()}?"
    elif memory_type == "failure":
        importance = 8
        follow_up_at = datetime.now(UTC) + timedelta(days=3)
        follow_up_prompt = f"How are you recovering from {title.lower()}?"
    elif memory_type == "project":
        importance = 7
        follow_up_at = (event_date + timedelta(days=2)) if event_date else datetime.now(UTC) + timedelta(days=5)
        follow_up_prompt = f"How is {title} progressing?"
    elif memory_type in {"relationship", "person"}:
        importance = 6
        follow_up_at = datetime.now(UTC) + timedelta(days=5)
        follow_up_prompt = f"How is your relationship with {title.split(' ')[0]} going?"
    elif memory_type == "promise":
        importance = 7
        follow_up_at = datetime.now(UTC) + timedelta(days=2)
        follow_up_prompt = f"Did you get to {title.lower()}?"
    elif memory_type == "follow_up":
        importance = 6
        follow_up_at = datetime.now(UTC) + timedelta(days=2)
        follow_up_prompt = f"Any update on {title.lower()}?"
    elif memory_type == "decision":
        importance = 5
    elif memory_type == "milestone":
        importance = 7
        follow_up_at = datetime.now(UTC) + timedelta(days=7)
        follow_up_prompt = "What did that milestone lead to?"
    elif memory_type == "emotional_pattern":
        importance = 6
        follow_up_at = datetime.now(UTC) + timedelta(days=4)
        follow_up_prompt = "Has that emotional pattern changed recently?"

    if not life_area:
        if memory_type in {"emotion", "reflection", "habit", "challenge", "failure", "emotional_pattern"}:
            life_area = None
        elif memory_type == "recurring_concern" and any(word in text.lower() for word in ("sales", "buying", "customer", "client", "business")):
            life_area = "business"
        elif memory_type in {"project", "important_event", "win", "decision", "milestone", "promise", "follow_up"}:
            life_area = "business" if any(word in text.lower() for word in ("client", "sales", "launch", "demo", "business", "project", "qring")) else None
        elif memory_type in {"relationship", "person"}:
            life_area = "relationships"

    if memory_type not in _RELATIONSHIP_MEMORY_TYPES and memory_type not in {"fact", "goal", "preference", "emotion", "habit", "reflection", "challenge"}:
        return None

    confidence = _confidence_for_candidate(memory_type, text, title, entities, life_area)
    requires_confirmation = confidence < _AUTO_SAVE_CONFIDENCE_THRESHOLD
    approval_status = "pending" if sensitive or requires_confirmation else "approved"
    return {
        "type": memory_type,
        "life_area": life_area,
        "title": title,
        "content": _normalise(text),
        "importance": importance,
        "confidence": confidence,
        "approval_status": approval_status,
        "memory_scope": "permanent",
        "expires_at": None,
        "suggested_reason": _suggested_reason_for_candidate(memory_type, confidence, sensitive),
        "sensitive": _is_sensitive(text),
        "user_approved": approval_status == "approved",
        "requires_confirmation": requires_confirmation,
        "mode": mode,
        "emotion": emotion,
        "event_date": event_date,
        "entities": entities or None,
        "sentiment": sentiment,
        "follow_up_at": follow_up_at,
        "follow_up_status": "pending" if follow_up_at else None,
        "follow_up_prompt": follow_up_prompt,
    }


def _memory_candidates_for(text: str, *, emotion: str | None = None, mode: str | None = None) -> list[dict[str, object]]:
    lower = text.lower()
    candidates: list[dict[str, object]] = []

    if _looks_like_event(text):
        candidates.append(_build_candidate("important_event", text, emotion=emotion, mode=mode))
    if _looks_like_project(text):
        candidates.append(_build_candidate("project", text, emotion=emotion, mode=mode))
    if _looks_like_concern(text):
        candidates.append(_build_candidate("recurring_concern", text, emotion=emotion, mode=mode))
    if _looks_like_win(text):
        candidates.append(_build_candidate("win", text, emotion=emotion, mode=mode))
    if _looks_like_failure(text):
        candidates.append(_build_candidate("failure", text, emotion=emotion, mode=mode))
    if _looks_like_relationship(text):
        candidates.append(_build_candidate("relationship", text, emotion=emotion, mode=mode))
        if _extract_entities(text):
            candidates.append(_build_candidate("person", text, emotion=emotion, mode=mode))
    if _looks_like_promise(text):
        candidates.append(_build_candidate("promise", text, emotion=emotion, mode=mode))
    if "follow up" in lower or "follow-up" in lower:
        candidates.append(_build_candidate("follow_up", text, emotion=emotion, mode=mode))
    if any(word in lower for word in ("decision", "decided", "choose", "chose")):
        candidates.append(_build_candidate("decision", text, emotion=emotion, mode=mode))
    if any(word in lower for word in ("milestone", "first", "landed", "signed", "booked")):
        candidates.append(_build_candidate("milestone", text, emotion=emotion, mode=mode))
    if emotion in {"sad", "anxious", "frustrated", "angry", "drained"}:
        candidates.append(_build_candidate("emotional_pattern", text, emotion=emotion, mode=mode))

    has_specialized = any(candidate is not None and candidate.get("type") != "fact" for candidate in candidates)
    if not has_specialized:
        fallback = _build_candidate(_memory_type_for(text), text, emotion=emotion, mode=mode)
        if fallback is not None:
            candidates.append(fallback)

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        key = (str(candidate["type"]), str(candidate["title"]).lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


async def recent_life_area_insight(db: AsyncSession, user_id: UUID, limit: int = 20) -> dict[str, object] | None:
    result = await db.execute(
        select(Memory.life_area)
        .where(
            Memory.user_id == user_id,
            _memory_visibility_condition(include_pending=False),
            Memory.life_area.is_not(None),
        )
        .order_by(Memory.created_at.desc())
        .limit(limit)
    )
    life_areas = [str(row[0]).lower() for row in result.all() if row and row[0]]
    if len(life_areas) < 3:
        return None

    counts = Counter(life_areas)
    area, count = counts.most_common(1)[0]
    total = sum(counts.values())
    if count < 3 or count / total < 0.45:
        return None

    nudge = _life_area_nudge(area)
    if not nudge:
        return None
    return {
        "life_area": area,
        "count": count,
        "total": total,
        "text": nudge,
    }


def _memory_type_for(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("want to", "goal", "aim", "trying to", "plan to")):
        return "goal"
    if any(word in lower for word in ("prefer", "like", "love", "don't like", "hate")):
        return "preference"
    if any(word in lower for word in ("friend", "wife", "husband", "mom", "dad", "sister", "brother")):
        return "relationship"
    if any(word in lower for word in ("felt", "feeling", "frustrated", "tired", "burned out", "anxious", "drained", "overwhelmed", "stressed")):
        return "emotion"
    if any(word in lower for word in ("habit", "every day", "usually", "often")):
        return "habit"
    if any(word in lower for word in ("lesson", "learned", "reflection", "review")):
        return "reflection"
    if any(word in lower for word in ("challenge", "problem", "stuck", "blocked")):
        return "challenge"
    if any(word in lower for word in ("win", "success", "progress", "accomplished")):
        return "win"
    return "fact"


def _is_sensitive(text: str) -> bool:
    lower = text.lower()
    return any(word in lower for word in _SENSITIVE_WORDS)


def _is_trivial(text: str) -> bool:
    normalized = _normalise(text)
    words = normalized.split()
    if len(words) >= 3:
        return False
    lower = normalized.lower()
    meaningful_signals = (
        "buy",
        "buying",
        "closed",
        "customer",
        "demo",
        "exhausted",
        "failed",
        "frustrat",
        "friend",
        "husband",
        "launch",
        "lost",
        "mentor",
        "prayer",
        "praying",
        "relationship",
        "sales",
        "stressed",
        "tired",
        "wife",
        "won",
        "workout",
    )
    return not any(signal in lower for signal in meaningful_signals)


async def create_memory(
    db: AsyncSession,
    user_id: UUID,
    *,
    type: str,
    life_area: str | None,
    title: str,
    content: str,
    importance: int = 1,
    confidence: float = 0.5,
    source_message_id: UUID | None = None,
    follow_up_at: datetime | None = None,
    follow_up_status: str | None = None,
    follow_up_prompt: str | None = None,
    event_date: datetime | None = None,
    entities: list[str] | dict | None = None,
    sentiment: str | None = None,
    approval_status: str | None = None,
    memory_scope: str = "permanent",
    expires_at: datetime | None = None,
    suggested_reason: str | None = None,
    edited_from_id: UUID | None = None,
    sensitive: bool = False,
    user_approved: bool = True,
    source_provider: str | None = None,
    source_item_id: UUID | None = None,
) -> Memory:
    if memory_scope == "temporary" and expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(days=_TEMPORARY_MEMORY_DEFAULT_DAYS)
    if approval_status not in {"approved", "pending", "rejected", "expired"}:
        approval_status = "pending" if sensitive or not user_approved else "approved"
    memory = Memory(
        user_id=user_id,
        type=type,
        life_area=life_area,
        title=title[:255],
        content=_normalise(content),
        importance=importance,
        confidence=confidence,
        source_message_id=source_message_id,
        follow_up_at=follow_up_at,
        follow_up_status=follow_up_status,
        follow_up_prompt=follow_up_prompt,
        event_date=event_date,
        entities=entities,
        sentiment=sentiment,
        embedding=embed_text(content),
        sensitive=sensitive,
        user_approved=user_approved,
        paused=False,
        approval_status=approval_status,
        memory_scope=memory_scope,
        expires_at=expires_at,
        suggested_reason=suggested_reason,
        edited_from_id=edited_from_id,
        source_provider=source_provider,
        source_item_id=source_item_id,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    from .memory_manager import memory_manager
    if memory.approval_status == "approved" and not memory.paused and (
        memory.memory_scope != "temporary" or memory.expires_at is None or _as_utc(memory.expires_at) > datetime.now(UTC)
    ):
        await memory_manager.index_row(db, memory)
    await record_audit(
        db,
        user_id,
        "memory.create",
        "memory",
        str(memory.id),
        {"type": type, "life_area": life_area, "sensitive": sensitive, "user_approved": user_approved},
    )
    await _sync_or_queue_knowledge_graph_links(memory)
    return memory


async def search_memories(
    db: AsyncSession,
    user_id: UUID,
    query: str,
    limit: int = 8,
    *,
    goal_titles: list[str] | None = None,
    goal_areas: list[str] | None = None,
    recent_summary: str | None = None,
    mode: str | None = None,
    emotion: str | None = None,
) -> list[Memory]:
    query_vec = embed_text(query)
    from .memory_manager import memory_manager

    semantic = await memory_manager.retrieve_query(
        db, user_id, query, limit=max(limit * 4, 32)
    )
    memory_ids = [
        UUID(str(item["id"]))
        for item in semantic["items"]
        if item.get("source_type") == "memory"
    ]
    if not memory_ids:
        return []
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.id.in_(memory_ids),
            _memory_visibility_condition(include_pending=False),
        )
    )
    rows = list(result.scalars().all())
    query_tokens = _tokenize(query)
    summary_tokens = _tokenize(recent_summary or "")
    goal_tokens = set().union(*(_tokenize(title) for title in (goal_titles or []))) if goal_titles else set()
    goal_area_tokens = {area.lower() for area in (goal_areas or []) if area}
    mode_tokens = {mode.lower()} if mode else set()
    emotion_tokens = {emotion.lower()} if emotion else set()

    now = datetime.now(UTC)

    def rank(memory: Memory) -> float:
        base = cosine_similarity(query_vec, memory.embedding if isinstance(memory.embedding, list) else None)
        text = f"{memory.title} {memory.content}".lower()
        text_tokens = _tokenize(text)
        score = base
        age_days = max((_as_utc(now) - _as_utc(memory.created_at)).days, 0)
        score += max(0.0, 0.09 - (age_days * 0.003))
        if goal_tokens and text_tokens & goal_tokens:
            score += 0.12
        if goal_area_tokens and memory.life_area and memory.life_area.lower() in goal_area_tokens:
            score += 0.08
        if summary_tokens and text_tokens & summary_tokens:
            score += 0.06
        if query_tokens and text_tokens & query_tokens:
            score += 0.04
        if not query_tokens or len(query_tokens) <= 2:
            score += min(memory.importance or 0, 10) * 0.012
            if memory.type in {"important_event", "win", "failure", "recurring_concern"}:
                score += 0.04
        if mode_tokens and memory.type in mode_tokens:
            score += 0.03
        if emotion_tokens and memory.type == "emotion":
            score += 0.02
        score += min(memory.importance or 0, 5) * 0.01
        score += max(min(memory.confidence or 0.0, 1.0), 0.0) * 0.01
        return score

    ranked = sorted(
        rows,
        key=rank,
        reverse=True,
    )
    return ranked[:limit]


async def update_memory(db: AsyncSession, user_id: UUID, memory_id: UUID, data: dict) -> Memory | None:
    result = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return None
    for key in (
        "type",
        "life_area",
        "title",
        "content",
        "importance",
        "confidence",
        "approval_status",
        "memory_scope",
        "expires_at",
        "suggested_reason",
        "edited_from_id",
        "follow_up_at",
        "follow_up_status",
        "follow_up_prompt",
        "event_date",
        "entities",
        "sentiment",
        "sensitive",
        "user_approved",
        "paused",
    ):
        if key in data and data[key] is not None:
            setattr(memory, key, data[key])
    memory.updated_at = datetime.now(UTC)
    if data.get("content"):
        memory.embedding = embed_text(str(data["content"]))
    if memory.memory_scope == "temporary" and memory.expires_at is None:
        memory.expires_at = datetime.now(UTC) + timedelta(days=_TEMPORARY_MEMORY_DEFAULT_DAYS)
    await db.commit()
    await db.refresh(memory)
    from .memory_manager import memory_manager
    if memory.approval_status == "approved" and not memory.paused and (
        memory.memory_scope != "temporary" or memory.expires_at is None or _as_utc(memory.expires_at) > datetime.now(UTC)
    ):
        await memory_manager.index_row(db, memory)
    else:
        await memory_manager.delete_source(db, user_id, "memory", str(memory.id))
    await record_audit(
        db,
        user_id,
        "memory.update",
        "memory",
        str(memory.id),
        {k: data.get(k) for k in data.keys()},
    )
    await _sync_or_queue_knowledge_graph_links(memory)
    return memory


async def delete_memory(db: AsyncSession, user_id: UUID, memory_id: UUID) -> bool:
    result = await db.execute(select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id))
    memory = result.scalar_one_or_none()
    if memory is None:
        return False
    await db.delete(memory)
    await db.commit()
    from .memory_manager import memory_manager
    await memory_manager.delete_source(db, user_id, "memory", str(memory_id))
    await record_audit(db, user_id, "memory.delete", "memory", str(memory_id))
    try:
        from .knowledge_graph_service import unlink_memory_links

        await unlink_memory_links(db, user_id, memory_id)
    except Exception:
        pass
    return True


async def pause_memory(db: AsyncSession, user_id: UUID, memory_id: UUID, paused: bool = True) -> Memory | None:
    return await update_memory(db, user_id, memory_id, {"paused": paused})


async def approve_memory(db: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    memory = await update_memory(db, user_id, memory_id, {"user_approved": True, "approval_status": "approved"})
    if memory is not None:
        await record_audit(db, user_id, "memory.approve", "memory", str(memory.id))
    return memory


async def deny_memory(db: AsyncSession, user_id: UUID, memory_id: UUID) -> bool:
    memory = await update_memory(db, user_id, memory_id, {"user_approved": False, "approval_status": "rejected"})
    if memory is not None:
        await record_audit(db, user_id, "memory.deny", "memory", str(memory_id))
        return True
    return False


async def reject_memory(db: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    memory = await update_memory(db, user_id, memory_id, {"user_approved": False, "approval_status": "rejected"})
    if memory is not None:
        await record_audit(db, user_id, "memory.reject", "memory", str(memory.id))
    return memory


async def make_memory_temporary(
    db: AsyncSession,
    user_id: UUID,
    memory_id: UUID,
    *,
    expires_at: datetime | None = None,
) -> Memory | None:
    payload: dict[str, object] = {"memory_scope": "temporary"}
    if expires_at is not None:
        payload["expires_at"] = expires_at
    memory = await update_memory(db, user_id, memory_id, payload)
    if memory is not None:
        await record_audit(db, user_id, "memory.make_temporary", "memory", str(memory.id))
    return memory


async def make_memory_permanent(db: AsyncSession, user_id: UUID, memory_id: UUID) -> Memory | None:
    memory = await update_memory(db, user_id, memory_id, {"memory_scope": "permanent", "expires_at": None})
    if memory is not None:
        await record_audit(db, user_id, "memory.make_permanent", "memory", str(memory.id))
    return memory


async def pending_memories(db: AsyncSession, user_id: UUID) -> list[Memory]:
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            Memory.approval_status == "pending",
            Memory.paused.is_(False),
        ).order_by(Memory.created_at.desc())
    )
    return list(result.scalars().all())


async def list_memories(db: AsyncSession, user_id: UUID) -> list[Memory]:
    result = await db.execute(
        select(Memory).where(
            Memory.user_id == user_id,
            _memory_visibility_condition(include_pending=True),
        ).order_by(Memory.created_at.desc())
    )
    return list(result.scalars().all())


async def export_memories(db: AsyncSession, user_id: UUID) -> list[dict]:
    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.approval_status != "rejected").order_by(Memory.created_at.asc())
    )
    out = []
    for memory in result.scalars().all():
        out.append(
            {
                "id": str(memory.id),
                "type": memory.type,
                "life_area": memory.life_area,
                "title": memory.title,
                "content": memory.content,
                "importance": memory.importance,
                "confidence": memory.confidence,
                "approval_status": memory.approval_status if not _memory_is_expired(memory) else "expired",
                "memory_scope": memory.memory_scope,
                "expires_at": memory.expires_at,
                "suggested_reason": memory.suggested_reason,
                "edited_from_id": memory.edited_from_id,
                "follow_up_at": memory.follow_up_at,
                "follow_up_status": memory.follow_up_status,
                "follow_up_prompt": memory.follow_up_prompt,
                "event_date": memory.event_date,
                "entities": memory.entities,
                "sentiment": memory.sentiment,
                "sensitive": memory.sensitive,
                "user_approved": memory.user_approved,
                "paused": memory.paused,
            }
        )
    await record_audit(db, user_id, "memory.export", "memory", details={"count": len(out)})
    return out


def extract_memories_from_message(message: str, *, emotion: str | None = None, mode: str | None = None) -> list[dict]:
    return [candidate for candidate in _memory_candidates_for(message, emotion=emotion, mode=mode) if candidate]


async def summarize_recent_conversations(db: AsyncSession, user_id: UUID, limit: int = 5) -> str:
    result = await db.execute(
        select(Message.content)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.user_id == user_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    texts = [row[0] for row in result.all()]
    return " | ".join(texts[::-1])


async def persist_extracted_memories(
    db: AsyncSession,
    user_id: UUID,
    source_message_id: UUID | None,
    message: str,
    *,
    emotion: str | None = None,
    mode: str | None = None,
) -> list[Memory]:
    created: list[Memory] = []
    for candidate in extract_memories_from_message(message, emotion=emotion, mode=mode):
        if await _is_duplicate_candidate(db, user_id, candidate):
            continue
        user_approved = bool(candidate["user_approved"])
        if candidate["sensitive"] and not user_approved:
            # Store the memory for visibility, but keep it out of retrieval until approved.
            pass
        memory = await create_memory(
            db,
            user_id,
            type=candidate["type"],
            life_area=candidate["life_area"],
            title=candidate["title"],
            content=candidate["content"],
            importance=candidate["importance"],
            confidence=candidate["confidence"],
            source_message_id=source_message_id,
            follow_up_at=candidate.get("follow_up_at"),
            follow_up_status=candidate.get("follow_up_status"),
            follow_up_prompt=candidate.get("follow_up_prompt"),
            event_date=candidate.get("event_date"),
            entities=candidate.get("entities"),
            sentiment=candidate.get("sentiment"),
            sensitive=candidate["sensitive"],
            user_approved=user_approved,
            approval_status=str(candidate.get("approval_status") or ("approved" if user_approved else "pending")),
            memory_scope=str(candidate.get("memory_scope") or "permanent"),
            expires_at=candidate.get("expires_at"),
            suggested_reason=candidate.get("suggested_reason"),
            source_provider=candidate.get("source_provider"),
            source_item_id=candidate.get("source_item_id"),
        )
        created.append(memory)
        project = await match_project_for_text(db, user_id, message)
        if project is not None and candidate["type"] in {"project", "important_event", "win", "failure", "decision", "milestone"}:
            await create_event(
                db,
                user_id,
                project.id,
                {
                    "event_type": candidate["type"],
                    "title": candidate["title"],
                    "description": candidate["content"],
                    "occurred_at": candidate.get("event_date") or datetime.now(UTC),
                    "source_type": "memory",
                    "source_id": memory.id,
                },
            )
    return created


async def memory_timeline(
    db: AsyncSession,
    user_id: UUID,
    *,
    life_area: str | None = None,
    type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 100,
) -> list[Memory]:
    q = select(Memory).where(Memory.user_id == user_id, _memory_visibility_condition(include_pending=False))
    if life_area:
        q = q.where(Memory.life_area == life_area)
    if type:
        q = q.where(Memory.type == type)
    if start_date is not None:
        q = q.where(or_(Memory.event_date >= start_date, Memory.created_at >= start_date))
    if end_date is not None:
        q = q.where(or_(Memory.event_date <= end_date, Memory.created_at <= end_date))
    q = q.order_by(func.coalesce(Memory.event_date, Memory.created_at).desc()).limit(limit)
    result = await db.execute(q)
    return list(result.scalars().all())


async def relationship_context(
    db: AsyncSession,
    user_id: UUID,
    *,
    limit: int = 5,
) -> dict[str, list[Memory]]:
    result = await db.execute(
        select(Memory)
        .where(
            Memory.user_id == user_id,
            _memory_visibility_condition(include_pending=False),
            Memory.type.in_(list(_RELATIONSHIP_MEMORY_TYPES)),
        )
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(limit * 3)
    )
    rows = list(result.scalars().all())
    grouped: dict[str, list[Memory]] = defaultdict(list)
    for memory in rows:
        grouped[memory.type].append(memory)
    return grouped


def memory_to_dict(memory: Memory) -> dict[str, object]:
    return {
        "id": str(memory.id),
        "user_id": str(memory.user_id),
        "type": memory.type,
        "life_area": memory.life_area,
        "title": memory.title,
        "content": memory.content,
        "importance": memory.importance,
        "confidence": memory.confidence,
        "approval_status": memory.approval_status if not _memory_is_expired(memory) else "expired",
        "memory_scope": memory.memory_scope,
        "expires_at": memory.expires_at,
        "suggested_reason": memory.suggested_reason,
        "edited_from_id": memory.edited_from_id,
        "follow_up_at": memory.follow_up_at,
        "follow_up_status": memory.follow_up_status,
        "follow_up_prompt": memory.follow_up_prompt,
        "event_date": memory.event_date,
        "entities": memory.entities,
        "sentiment": memory.sentiment,
        "sensitive": memory.sensitive,
        "user_approved": memory.user_approved,
        "paused": memory.paused,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _should_defer_graph_linking() -> bool:
    return _SETTINGS.aipal_env.lower() in {"production", "prod"}


async def _sync_knowledge_graph_links(db: AsyncSession, memory: Memory) -> None:
    try:
        from .knowledge_graph_service import link_memory_to_entities

        await link_memory_to_entities(db, memory.user_id, memory.id)
    except Exception:
        # Knowledge graph linking must never block memory writes.
        return


async def _sync_or_queue_knowledge_graph_links(memory: Memory) -> None:
    if not _should_defer_graph_linking():
        async with async_session() as db:
            await _sync_knowledge_graph_links(db, memory)
        return

    async def _background_link() -> None:
        try:
            async with async_session() as db:
                await _sync_knowledge_graph_links(db, memory)
        except Exception:
            return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        async with async_session() as db:
            await _sync_knowledge_graph_links(db, memory)
        return
    asyncio.create_task(_background_link())
