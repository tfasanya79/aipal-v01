from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KnowledgeEdge, KnowledgeEntity, Memory, MemoryEntityLink

_KNOWN_PROJECT_NAMES = ("Qring", "CampusCart", "FitAccess", "AiPal", "Sammya")
_RELATIONSHIP_WORDS = (
    "wife",
    "husband",
    "spouse",
    "partner",
    "friend",
    "mentor",
    "family",
    "client",
    "customer",
    "investor",
    "colleague",
    "coworker",
)
_STOPWORDS = {
    "A",
    "An",
    "And",
    "At",
    "But",
    "For",
    "From",
    "I",
    "In",
    "It",
    "My",
    "Of",
    "On",
    "Or",
    "The",
    "To",
    "We",
    "With",
    "You",
    "Your",
}
_PROJECT_WORDS = ("demo", "launch", "launches", "project", "build", "ship", "product", "startup", "client", "customer", "pipeline")
_EVENT_WORDS = ("demo", "meeting", "call", "presentation", "launch", "deadline", "interview", "review", "trip", "event")
_CONCERN_WORDS = ("sales", "buying", "nobody", "stuck", "blocked", "worried", "frustrated", "concern", "struggling", "can't")
_WIN_WORDS = ("closed", "won", "booked", "signed", "finished", "completed", "shipped", "launched")
_FAILURE_WORDS = ("failed", "lost", "missed", "broke", "couldn't", "didn't", "did not")
_GENERIC_NAME_EXCLUSIONS = {
    "concern",
    "customer",
    "customers",
    "demo",
    "event",
    "launch",
    "memory",
    "meeting",
    "project",
    "sales",
    "topic",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _lower(value: str | None) -> str:
    return _normalize(value).lower()


def _iter_strings(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_iter_strings(item))
        return out
    if isinstance(value, (list, tuple, set)):
        out: list[str] = []
        for item in value:
            out.extend(_iter_strings(item))
        return out
    return [str(value)]


def _safe_aliases(aliases) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for alias in _iter_strings(aliases):
        cleaned = _normalize(alias)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _memory_is_expired(memory: Memory, now: datetime | None = None) -> bool:
    if memory.approval_status == "expired":
        return True
    if memory.memory_scope != "temporary" or memory.expires_at is None:
        return False
    current = now or _utcnow()
    expires_at = memory.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= current


def _memory_is_visible(memory: Memory, now: datetime | None = None) -> bool:
    if memory.paused:
        return False
    if memory.approval_status != "approved":
        return False
    return not _memory_is_expired(memory, now)


def _memory_text(memory: Memory) -> str:
    return _normalize(f"{memory.title} {memory.content}")


def _extract_project_candidates(text: str) -> list[dict[str, object]]:
    lower = text.lower()
    candidates: list[dict[str, object]] = []
    for project in _KNOWN_PROJECT_NAMES:
        if project.lower() in lower:
            candidates.append(
                {
                    "entity_type": "project",
                    "name": project,
                    "aliases": [project.lower()],
                    "description": f"Project referenced in memory: {project}",
                    "confidence": 0.96,
                    "metadata": {"source": "memory_text"},
                    "relation_type": "related_to",
                    "priority": 1,
                }
            )
    if not candidates and any(word in lower for word in _PROJECT_WORDS):
        match = re.search(r"\b([A-Z][a-zA-Z0-9&'-]{1,})\b", text)
        if match:
            name = match.group(1)
            candidates.append(
                {
                    "entity_type": "project",
                    "name": name,
                    "aliases": [name.lower()],
                    "description": f"Project mentioned in memory: {name}",
                    "confidence": 0.72,
                    "metadata": {"source": "heuristic"},
                    "relation_type": "related_to",
                    "priority": 1,
                }
            )
    return candidates


def _extract_event_candidates(memory: Memory, text: str) -> list[dict[str, object]]:
    lower = text.lower()
    if memory.type not in {"important_event", "milestone", "decision", "follow_up", "promise", "project"} and not any(
        word in lower for word in _EVENT_WORDS
    ):
        return []
    title = memory.title or "Event"
    return [
        {
            "entity_type": "event",
            "name": _normalize(title)[:255] or "Event",
            "aliases": [title.lower()],
            "description": memory.content[:240] if memory.content else None,
            "confidence": 0.88 if memory.type in {"important_event", "milestone"} else 0.72,
            "metadata": {"source_memory_type": memory.type},
            "relation_type": "belongs_to",
            "priority": 2,
        }
    ]


def _extract_concern_candidates(memory: Memory, text: str) -> list[dict[str, object]]:
    lower = text.lower()
    if memory.type != "recurring_concern" and not any(word in lower for word in _CONCERN_WORDS):
        return []
    title = memory.title
    if not title or title.lower() in {"memory", "fact"}:
        if any(word in lower for word in ("sales", "buying", "customer", "client")):
            title = "Sales concern"
        else:
            title = "Recurring concern"
    return [
        {
            "entity_type": "topic",
            "name": _normalize(title)[:255],
            "aliases": [title.lower()],
            "description": memory.content[:240] if memory.content else None,
            "confidence": 0.84,
            "metadata": {"source_memory_type": memory.type},
            "relation_type": "blocks",
            "priority": 3,
        }
    ]


def _extract_people_candidates(text: str) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for word in _RELATIONSHIP_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", text, flags=re.IGNORECASE):
            name = word.title()
            candidates.append(
                {
                    "entity_type": "relationship",
                    "name": name,
                    "aliases": [word.lower()],
                    "description": f"Relationship context: {word}",
                    "confidence": 0.72,
                    "metadata": {"source": "relationship_term"},
                    "relation_type": "related_to",
                    "priority": 4,
                }
            )
    for match in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", text):
        if match in _STOPWORDS or match.lower() in {project.lower() for project in _KNOWN_PROJECT_NAMES}:
            continue
        if match.lower() in _GENERIC_NAME_EXCLUSIONS:
            continue
        if any(term.lower() == match.lower() for term in _RELATIONSHIP_WORDS):
            continue
        candidates.append(
            {
                "entity_type": "person",
                "name": match[:255],
                "aliases": [match.lower()],
                "description": f"Person mentioned in memory: {match}",
                "confidence": 0.86,
                "metadata": {"source": "capitalized_name"},
                "relation_type": "mentioned_with",
                "priority": 4,
            }
        )
    return candidates


def _memory_visibility_condition():
    now = _utcnow()
    return and_(
        Memory.user_approved.is_(True),
        Memory.paused.is_(False),
        Memory.approval_status == "approved",
        or_(Memory.memory_scope != "temporary", Memory.expires_at.is_(None), Memory.expires_at > now),
    )


def _entity_payload(entity: KnowledgeEntity) -> dict[str, object]:
    return {
        "id": str(entity.id),
        "user_id": str(entity.user_id),
        "entity_type": entity.entity_type,
        "name": entity.name,
        "aliases": list(entity.aliases or []) if isinstance(entity.aliases, list) else entity.aliases,
        "description": entity.description,
        "metadata": entity.metadata_json,
        "confidence": float(entity.confidence or 0.0),
        "created_at": entity.created_at,
        "updated_at": entity.updated_at,
    }


def _edge_payload(edge: KnowledgeEdge) -> dict[str, object]:
    return {
        "id": str(edge.id),
        "user_id": str(edge.user_id),
        "source_entity_id": str(edge.source_entity_id),
        "target_entity_id": str(edge.target_entity_id),
        "relation_type": edge.relation_type,
        "weight": float(edge.weight or 0.0),
        "evidence_memory_id": str(edge.evidence_memory_id) if edge.evidence_memory_id else None,
        "evidence_message_id": str(edge.evidence_message_id) if edge.evidence_message_id else None,
        "created_at": edge.created_at,
        "updated_at": edge.updated_at,
    }


def _memory_payload(memory: Memory) -> dict[str, object]:
    return {
        "id": str(memory.id),
        "title": memory.title,
        "type": memory.type,
        "life_area": memory.life_area,
        "content": memory.content,
        "confidence": float(memory.confidence or 0.0),
        "sentiment": memory.sentiment,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def _rank_candidate(query: str, entity: KnowledgeEntity) -> float:
    haystack = " ".join(
        [
            entity.name or "",
            " ".join(_safe_aliases(entity.aliases)),
            entity.description or "",
            " ".join(_safe_aliases(entity.metadata_json)) if isinstance(entity.metadata_json, (list, dict)) else "",
        ]
    ).lower()
    if not query:
        return float(entity.confidence or 0.0)
    score = float(entity.confidence or 0.0)
    q = query.lower()
    if q == entity.name.lower():
        score += 2.0
    if q in haystack:
        score += 1.0
    score += SequenceMatcher(None, q, haystack).ratio()
    return score


async def _find_user_entity(db: AsyncSession, user_id: UUID, entity_type: str, name: str) -> KnowledgeEntity | None:
    result = await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id))
    normalized = _normalize(name).lower()
    for row in result.scalars().all():
        aliases = {row.name.lower(), *{alias.lower() for alias in _safe_aliases(row.aliases)}}
        if row.entity_type == entity_type and normalized in aliases:
            return row
    return None


async def upsert_entity(
    db: AsyncSession,
    user_id: UUID,
    entity_type: str,
    name: str,
    aliases=None,
    description: str | None = None,
    confidence: float = 0.5,
    metadata: dict | list | None = None,
) -> KnowledgeEntity:
    candidate_aliases = _safe_aliases(aliases)
    candidate_aliases.append(_normalize(name))
    existing = await _find_user_entity(db, user_id, entity_type, name)
    if existing is None:
        existing = KnowledgeEntity(
            user_id=user_id,
            entity_type=entity_type,
            name=_normalize(name)[:255],
            aliases=candidate_aliases,
            description=description,
            metadata_json=metadata,
            confidence=confidence,
        )
        db.add(existing)
    else:
        merged_aliases = _safe_aliases(existing.aliases) + [alias for alias in candidate_aliases if alias.lower() not in {a.lower() for a in _safe_aliases(existing.aliases)}]
        existing.aliases = merged_aliases
        if description and not existing.description:
            existing.description = description
        if metadata:
            existing.metadata_json = metadata
        existing.confidence = max(float(existing.confidence or 0.0), confidence)
        existing.updated_at = _utcnow()
    await db.commit()
    await db.refresh(existing)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, existing)
    return existing


async def create_edge(
    db: AsyncSession,
    user_id: UUID,
    source: KnowledgeEntity,
    target: KnowledgeEntity,
    relation_type: str,
    evidence: dict | Memory | None = None,
    weight: float = 1.0,
) -> KnowledgeEdge:
    if source.id == target.id:
        raise ValueError("Edges must connect two different entities")

    evidence_memory_id = None
    evidence_message_id = None
    if isinstance(evidence, Memory):
        evidence_memory_id = evidence.id
        evidence_message_id = evidence.source_message_id
    elif isinstance(evidence, dict):
        evidence_memory_id = evidence.get("memory_id")
        evidence_message_id = evidence.get("message_id")

    result = await db.execute(
        select(KnowledgeEdge).where(
            KnowledgeEdge.user_id == user_id,
            KnowledgeEdge.source_entity_id == source.id,
            KnowledgeEdge.target_entity_id == target.id,
            KnowledgeEdge.relation_type == relation_type,
            KnowledgeEdge.evidence_memory_id == evidence_memory_id,
            KnowledgeEdge.evidence_message_id == evidence_message_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = KnowledgeEdge(
            user_id=user_id,
            source_entity_id=source.id,
            target_entity_id=target.id,
            relation_type=relation_type,
            weight=weight,
            evidence_memory_id=evidence_memory_id,
            evidence_message_id=evidence_message_id,
        )
        db.add(row)
    else:
        row.weight = max(float(row.weight or 0.0), weight)
        row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    from .memory_manager import memory_manager
    await memory_manager.index_row(db, row)
    return row


def _relation_for(candidate: dict[str, object], memory: Memory) -> str:
    relation = str(candidate.get("relation_type") or "related_to")
    if candidate.get("entity_type") == "event":
        return "belongs_to"
    if candidate.get("entity_type") == "topic" and memory.type == "recurring_concern":
        return "blocks"
    if memory.type == "win":
        return "supports"
    if memory.type == "failure":
        return "blocks"
    return relation


async def _clear_memory_links(db: AsyncSession, user_id: UUID, memory_id: UUID) -> None:
    await db.execute(
        delete(MemoryEntityLink).where(MemoryEntityLink.user_id == user_id, MemoryEntityLink.memory_id == memory_id)
    )
    await db.execute(
        delete(KnowledgeEdge).where(KnowledgeEdge.user_id == user_id, KnowledgeEdge.evidence_memory_id == memory_id)
    )
    await db.commit()


async def unlink_memory_links(db: AsyncSession, user_id: UUID, memory_id: UUID) -> None:
    await _clear_memory_links(db, user_id, memory_id)


async def _select_primary_project_entity(
    db: AsyncSession,
    user_id: UUID,
    project_candidates: list[KnowledgeEntity],
    memory: Memory,
) -> KnowledgeEntity | None:
    if project_candidates:
        return sorted(project_candidates, key=lambda row: (float(row.confidence or 0.0), row.created_at), reverse=True)[0]
    if memory.type not in {"recurring_concern", "important_event", "win", "failure", "project", "decision", "milestone"}:
        return None
    result = await db.execute(
        select(KnowledgeEntity)
        .where(KnowledgeEntity.user_id == user_id, KnowledgeEntity.entity_type == "project")
        .order_by(KnowledgeEntity.confidence.desc(), KnowledgeEntity.created_at.desc())
    )
    rows = list(result.scalars().all())
    if len(rows) == 1:
        return rows[0]
    if rows:
        text = _memory_text(memory).lower()
        exact_matches = [
            row
            for row in rows
            if row.name.lower() in text or any(alias.lower() in text for alias in _safe_aliases(row.aliases))
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            return sorted(exact_matches, key=lambda row: (float(row.confidence or 0.0), row.created_at), reverse=True)[0]
    return None


async def extract_entities_from_memory(memory: Memory) -> list[dict[str, object]]:
    text = _memory_text(memory)
    if not text:
        return []
    candidates: list[dict[str, object]] = []

    if isinstance(memory.entities, list):
        for entity in memory.entities:
            name = _normalize(str(entity))
            if name:
                candidates.append(
                    {
                        "entity_type": "topic",
                        "name": name,
                        "aliases": [name.lower()],
                        "description": f"Entity surfaced from memory payload: {name}",
                        "confidence": 0.7,
                        "metadata": {"source": "memory.entities"},
                        "relation_type": "related_to",
                        "priority": 5,
                    }
                )
    elif isinstance(memory.entities, dict):
        for value in _iter_strings(memory.entities):
            name = _normalize(value)
            if name:
                candidates.append(
                    {
                        "entity_type": "topic",
                        "name": name,
                        "aliases": [name.lower()],
                        "description": f"Entity surfaced from memory payload: {name}",
                        "confidence": 0.7,
                        "metadata": {"source": "memory.entities"},
                        "relation_type": "related_to",
                        "priority": 5,
                    }
                )

    candidates.extend(_extract_project_candidates(text))
    candidates.extend(_extract_event_candidates(memory, text))
    candidates.extend(_extract_concern_candidates(memory, text))
    candidates.extend(_extract_people_candidates(text))

    if not candidates:
        return []

    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for candidate in sorted(candidates, key=lambda item: int(item.get("priority", 10))):
        key = (str(candidate["entity_type"]), str(candidate["name"]).lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


async def link_memory_to_entities(db: AsyncSession, user_id: UUID, memory_id: UUID) -> list[MemoryEntityLink]:
    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id, Memory.id == memory_id)
    )
    memory = result.scalar_one_or_none()
    if memory is None:
        return []

    await _clear_memory_links(db, user_id, memory_id)
    if not _memory_is_visible(memory):
        return []

    candidates = await extract_entities_from_memory(memory)
    if not candidates:
        return []

    created_entities: list[KnowledgeEntity] = []
    for candidate in candidates:
        entity = await upsert_entity(
            db,
            user_id,
            str(candidate["entity_type"]),
            str(candidate["name"]),
            aliases=candidate.get("aliases"),
            description=candidate.get("description"),
            confidence=float(candidate.get("confidence", 0.5)),
            metadata=candidate.get("metadata"),
        )
        created_entities.append(entity)

    project_entities = [entity for entity in created_entities if entity.entity_type == "project"]
    primary_project = await _select_primary_project_entity(db, user_id, project_entities, memory)

    links: list[MemoryEntityLink] = []
    for entity, candidate in zip(created_entities, candidates, strict=False):
        link = MemoryEntityLink(
            user_id=user_id,
            memory_id=memory_id,
            entity_id=entity.id,
            confidence=float(candidate.get("confidence", 0.5)),
        )
        db.add(link)
        links.append(link)

    await db.commit()

    for entity, candidate in zip(created_entities, candidates, strict=False):
        if primary_project is None or entity.id == primary_project.id:
            continue
        relation = _relation_for(candidate, memory)
        await create_edge(
            db,
            user_id,
            entity,
            primary_project,
            relation,
            evidence=memory,
            weight=float(candidate.get("confidence", 1.0)),
        )

    if primary_project is not None:
        await db.refresh(primary_project)
    return links


async def get_entity(db: AsyncSession, user_id: UUID, entity_id: UUID) -> KnowledgeEntity | None:
    result = await db.execute(
        select(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id, KnowledgeEntity.id == entity_id)
    )
    return result.scalar_one_or_none()


async def search_entities(db: AsyncSession, user_id: UUID, query: str, *, entity_type: str | None = None) -> list[KnowledgeEntity]:
    result = await db.execute(
        select(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id)
    )
    rows = list(result.scalars().all())
    if entity_type:
        rows = [row for row in rows if row.entity_type == entity_type]
    query = _normalize(query)
    if not query:
        return sorted(rows, key=lambda row: (float(row.confidence or 0.0), row.created_at), reverse=True)
    scored = sorted(rows, key=lambda row: _rank_candidate(query, row), reverse=True)
    return [row for row in scored if query.lower() in " ".join([row.name, " ".join(_safe_aliases(row.aliases)), row.description or ""]).lower() or _rank_candidate(query, row) > 0.5]


async def get_entity_graph(db: AsyncSession, user_id: UUID, entity_id: UUID) -> dict[str, object] | None:
    entity = await get_entity(db, user_id, entity_id)
    if entity is None:
        return None

    edge_result = await db.execute(
        select(KnowledgeEdge)
        .where(
            KnowledgeEdge.user_id == user_id,
            or_(KnowledgeEdge.source_entity_id == entity_id, KnowledgeEdge.target_entity_id == entity_id),
        )
        .order_by(KnowledgeEdge.created_at.desc())
    )
    edges = list(edge_result.scalars().all())
    neighbor_ids = {
        edge.target_entity_id if edge.source_entity_id == entity_id else edge.source_entity_id
        for edge in edges
        if edge.source_entity_id != edge.target_entity_id
    }
    neighbors: list[KnowledgeEntity] = []
    if neighbor_ids:
        neighbor_result = await db.execute(
            select(KnowledgeEntity).where(
                KnowledgeEntity.user_id == user_id,
                KnowledgeEntity.id.in_(list(neighbor_ids)),
            )
        )
        neighbors = list(neighbor_result.scalars().all())

    memory_result = await db.execute(
        select(Memory)
        .join(MemoryEntityLink, MemoryEntityLink.memory_id == Memory.id)
        .where(
            MemoryEntityLink.user_id == user_id,
            MemoryEntityLink.entity_id == entity_id,
            _memory_visibility_condition(),
        )
        .order_by(Memory.created_at.desc())
    )
    memories = list(memory_result.scalars().all())
    return {
        "entity": _entity_payload(entity),
        "related_entities": [_entity_payload(row) for row in neighbors],
        "related_memories": [_memory_payload(row) for row in memories],
        "edges": [_edge_payload(edge) for edge in edges],
    }


async def get_user_graph_summary(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    entity_result = await db.execute(
        select(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id).order_by(KnowledgeEntity.confidence.desc(), KnowledgeEntity.created_at.desc())
    )
    entities = list(entity_result.scalars().all())
    edge_result = await db.execute(select(KnowledgeEdge).where(KnowledgeEdge.user_id == user_id))
    edges = list(edge_result.scalars().all())
    memory_result = await db.execute(select(Memory).where(Memory.user_id == user_id, _memory_visibility_condition()))
    memories = list(memory_result.scalars().all())

    type_counts = Counter(entity.entity_type for entity in entities)
    relation_counts = Counter(edge.relation_type for edge in edges)
    project_counts = Counter()
    person_counts = Counter()
    topic_counts = Counter()
    for edge in edges:
        source = next((entity for entity in entities if entity.id == edge.source_entity_id), None)
        target = next((entity for entity in entities if entity.id == edge.target_entity_id), None)
        for entity in (source, target):
            if entity is None:
                continue
            if entity.entity_type == "project":
                project_counts[entity.name] += 1
            elif entity.entity_type == "person":
                person_counts[entity.name] += 1
            elif entity.entity_type == "topic":
                topic_counts[entity.name] += 1

    patterns = await detect_patterns(db, user_id)
    return {
        "counts": {
            "entities": len(entities),
            "edges": len(edges),
            "memories": len(memories),
            "entity_types": dict(type_counts),
        },
        "top_entities": [
            {
                "name": entity.name,
                "entity_type": entity.entity_type,
                "confidence": float(entity.confidence or 0.0),
            }
            for entity in entities[:10]
        ],
        "top_projects": [{"name": name, "count": count} for name, count in project_counts.most_common(5)],
        "top_people": [{"name": name, "count": count} for name, count in person_counts.most_common(5)],
        "top_topics": [{"name": name, "count": count} for name, count in topic_counts.most_common(5)],
        "relation_counts": dict(relation_counts),
        "recent_memories": [_memory_payload(memory) for memory in memories[:10]],
        "patterns": patterns,
    }


async def detect_patterns(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    entity_result = await db.execute(
        select(KnowledgeEntity).where(KnowledgeEntity.user_id == user_id).order_by(KnowledgeEntity.created_at.desc())
    )
    entities = list(entity_result.scalars().all())
    edge_result = await db.execute(select(KnowledgeEdge).where(KnowledgeEdge.user_id == user_id))
    edges = list(edge_result.scalars().all())
    memory_result = await db.execute(select(Memory).where(Memory.user_id == user_id, _memory_visibility_condition()))
    memories = list(memory_result.scalars().all())

    project_counts = Counter()
    concern_counts = Counter()
    person_counts = Counter()
    for entity in entities:
        if entity.entity_type == "project":
            linked = sum(1 for edge in edges if edge.source_entity_id == entity.id or edge.target_entity_id == entity.id)
            project_counts[entity.name] = linked
        elif entity.entity_type == "topic":
            linked = sum(1 for edge in edges if edge.source_entity_id == entity.id or edge.target_entity_id == entity.id)
            concern_counts[entity.name] = linked
        elif entity.entity_type == "person":
            linked = sum(1 for edge in edges if edge.source_entity_id == entity.id or edge.target_entity_id == entity.id)
            person_counts[entity.name] = linked

    patterns: list[str] = []
    if project_counts:
        name, count = project_counts.most_common(1)[0]
        patterns.append(f"{name} appears across {count} linked memories or relationships.")
    if concern_counts:
        name, count = concern_counts.most_common(1)[0]
        patterns.append(f"{name} keeps showing up as a recurring theme.")
    if person_counts:
        name, count = person_counts.most_common(1)[0]
        patterns.append(f"{name} is mentioned repeatedly in your conversations.")
    if memories and any(memory.sentiment == "negative" for memory in memories[-8:]):
        patterns.append("Recent memories lean toward stress or frustration in a few areas.")
    return {
        "patterns": patterns,
        "projects": [{"name": name, "count": count} for name, count in project_counts.most_common(5)],
        "concerns": [{"name": name, "count": count} for name, count in concern_counts.most_common(5)],
        "people": [{"name": name, "count": count} for name, count in person_counts.most_common(5)],
    }


async def rebuild_user_graph(db: AsyncSession, user_id: UUID) -> dict[str, object]:
    await db.execute(delete(MemoryEntityLink).where(MemoryEntityLink.user_id == user_id))
    await db.execute(delete(KnowledgeEdge).where(KnowledgeEdge.user_id == user_id))
    await db.commit()
    result = await db.execute(
        select(Memory).where(Memory.user_id == user_id, _memory_visibility_condition()).order_by(Memory.created_at.asc())
    )
    memories = list(result.scalars().all())
    linked = 0
    for memory in memories:
        links = await link_memory_to_entities(db, user_id, memory.id)
        linked += len(links)
    summary = await get_user_graph_summary(db, user_id)
    summary["relinked_memories"] = len(memories)
    summary["created_links"] = linked
    return summary
