"""Phase 5 two-stage memory retrieval for the single conversation brain."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time as day_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Text, cast, delete, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    BusinessProject,
    BusinessProjectEvent,
    CalendarEventCache,
    Goal,
    KnowledgeEdge,
    KnowledgeEntity,
    Memory,
    MemoryIndexStatus,
    MemorySearchDocument,
    Message,
    Reminder,
    Task,
    TodayItem,
    User,
    UserProfile,
)
from ..timezone_util import user_local_today
from .embedding_service import EmbeddingFunction, cosine_similarity, embed_text_semantic

INDEX_SCHEMA_VERSION = 1
SEARCH_CANDIDATE_LIMIT = 160


@dataclass(frozen=True, slots=True)
class SearchDocument:
    source_type: str
    source_id: str
    title: str
    content: str
    metadata: dict[str, Any]
    updated_at: datetime


def _utc(value: datetime | None) -> datetime:
    result = value or datetime.now(UTC)
    return result.replace(tzinfo=UTC) if result.tzinfo is None else result.astimezone(UTC)


def _json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, sort_keys=True)


def _memory_visible(row: Memory, *, now: datetime | None = None) -> bool:
    if row.paused or row.approval_status != "approved" or not row.user_approved:
        return False
    if row.memory_scope != "temporary" or row.expires_at is None:
        return True
    return _utc(row.expires_at) > (now or datetime.now(UTC))


def _lsh_buckets(vector: list[float]) -> tuple[str, str, str, str]:
    """Four deterministic random-hyperplane bands for bounded fallback search."""
    buckets: list[str] = []
    for band in range(4):
        bits = 0
        for plane in range(8):
            projection = 0.0
            seed = (band + 1) * 104729 + (plane + 1) * 13007
            for index, value in enumerate(vector):
                sign = 1.0 if ((index * 2654435761 + seed) & 1) else -1.0
                projection += value * sign
            if projection >= 0:
                bits |= 1 << plane
        buckets.append(f"{band}:{bits:02x}")
    return tuple(buckets)  # type: ignore[return-value]


def _vector_values(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, list):
        return [float(item) for item in value]
    if hasattr(value, "tolist"):
        return [float(item) for item in value.tolist()]
    try:
        return [float(item) for item in value]
    except TypeError:
        return None


def _rank_candidate_indexes(
    query: list[float],
    candidates: list[Any],
    limit: int,
) -> list[int]:
    """Rank vectors outside the event loop using native math when available.

    SQLite is a development fallback, but it still needs to remain responsive
    under concurrent turns. Ranking 160 dense 1536-dimensional vectors with
    Python loops monopolized the event loop for more than two seconds at 20
    concurrent queries. NumPy performs the same cosine calculation in native
    code; the thread boundary also keeps request cancellation and audio ingress
    responsive while ranking runs.
    """
    if not candidates or limit <= 0:
        return []
    try:
        import numpy as np

        query_vector = np.asarray(query, dtype=np.float32)
        width = len(query_vector)
        matrix = np.zeros((len(candidates), width), dtype=np.float32)
        for index, raw_vector in enumerate(candidates):
            vector = _vector_values(raw_vector)
            if vector:
                size = min(width, len(vector))
                matrix[index, :size] = vector[:size]
        query_norm = float(np.linalg.norm(query_vector)) or 1.0
        row_norms = np.linalg.norm(matrix, axis=1)
        denominators = np.maximum(row_norms * query_norm, 1e-12)
        scores = (matrix @ query_vector) / denominators
        count = min(limit, len(candidates))
        if count == len(candidates):
            return np.argsort(-scores, kind="stable").tolist()
        selected = np.argpartition(-scores, count - 1)[:count]
        return selected[np.argsort(-scores[selected], kind="stable")].tolist()
    except ImportError:
        scores = [
            cosine_similarity(query, _vector_values(vector))
            for vector in candidates
        ]
        return sorted(range(len(scores)), key=scores.__getitem__, reverse=True)[:limit]


def _indexed_document_visible(row: MemorySearchDocument, *, now: datetime) -> bool:
    if row.source_type != "memory":
        return True
    metadata = dict(row.metadata_json or {})
    if (
        metadata.get("approval_status") != "approved"
        or metadata.get("user_approved") is False
        or metadata.get("paused") is True
    ):
        return False
    if metadata.get("memory_scope") != "temporary":
        return True
    raw_expiry = str(metadata.get("expires_at") or "").strip()
    if not raw_expiry:
        return True
    try:
        return _utc(datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))) > now
    except ValueError:
        # Visibility metadata fails closed; a source update/backfill can repair
        # the projection without exposing questionable context in the meantime.
        return False


def _document(row: Any) -> SearchDocument:
    if isinstance(row, Memory):
        return SearchDocument("memory", str(row.id), row.title, row.content, {
            "type": row.type, "life_area": row.life_area, "importance": row.importance,
            "confidence": row.confidence, "approval_status": row.approval_status,
            "memory_scope": row.memory_scope, "expires_at": str(row.expires_at or ""),
            "user_approved": row.user_approved, "paused": row.paused,
        }, _utc(row.updated_at))
    if isinstance(row, BusinessProject):
        content = " ".join(filter(None, [row.description, _json_text(row.goals), _json_text(row.key_people), _json_text(row.risks), _json_text(row.opportunities)]))
        return SearchDocument("project", str(row.id), row.name, content, {"status": row.status}, _utc(row.updated_at))
    if isinstance(row, BusinessProjectEvent):
        return SearchDocument("project_event", str(row.id), row.title, row.description or "", {"project_id": str(row.project_id), "event_type": row.event_type, "occurred_at": row.occurred_at.isoformat()}, _utc(row.created_at))
    if isinstance(row, KnowledgeEntity):
        content = " ".join(filter(None, [row.description, _json_text(row.aliases), _json_text(row.metadata_json)]))
        source_type = "person" if row.entity_type in {"person", "relationship"} else "knowledge_entity"
        return SearchDocument(source_type, str(row.id), row.name, content, {"entity_type": row.entity_type, "confidence": float(row.confidence or 0)}, _utc(row.updated_at))
    if isinstance(row, KnowledgeEdge):
        return SearchDocument("knowledge_edge", str(row.id), row.relation_type, f"{row.source_entity_id} {row.relation_type} {row.target_entity_id}", {"source_entity_id": str(row.source_entity_id), "target_entity_id": str(row.target_entity_id), "weight": float(row.weight or 0)}, _utc(row.updated_at))
    if isinstance(row, Goal):
        return SearchDocument("goal", str(row.id), row.title, row.description or "", {"status": row.status, "priority": row.priority, "life_area": row.life_area, "target_date": str(row.target_date or "")}, _utc(row.updated_at))
    if isinstance(row, Task):
        return SearchDocument("task", str(row.id), row.title, row.notes or "", {"status": row.status, "priority": row.priority, "due_at": str(row.due_at or ""), "goal_id": str(row.goal_id or "")}, _utc(row.updated_at))
    if isinstance(row, Reminder):
        return SearchDocument("reminder", str(row.id), row.title, f"Reminder at {row.remind_at.isoformat()} {row.recurrence_rule or ''}", {"status": row.status, "remind_at": row.remind_at.isoformat(), "task_id": row.task_id}, _utc(row.updated_at))
    if isinstance(row, CalendarEventCache):
        return SearchDocument("calendar", str(row.id), row.title, f"Calendar event from {row.starts_at.isoformat()} to {row.ends_at.isoformat() if row.ends_at else 'unspecified'}", {"starts_at": row.starts_at.isoformat(), "ends_at": row.ends_at.isoformat() if row.ends_at else None}, _utc(row.imported_at))
    if isinstance(row, TodayItem):
        content = " ".join(filter(None, [row.description, _json_text(row.metadata_json)]))
        return SearchDocument("today", str(row.id), row.title, content, {"type": row.type, "status": row.status, "start_time": str(row.start_time or ""), "due_at": str(row.due_at or "")}, _utc(row.updated_at))
    if isinstance(row, Message):
        return SearchDocument("recent_discussion", str(row.id), f"{row.role} conversation message", row.content, {"role": row.role, "conversation_id": str(row.conversation_id), "emotion": row.emotion, "intent": row.intent, "source": row.source}, _utc(row.created_at))
    raise TypeError(f"Unsupported memory index source: {type(row).__name__}")


class MemoryManager:
    """Owns stable preload, semantic retrieval, and the rebuildable index."""

    def __init__(self, embedder: EmbeddingFunction = embed_text_semantic) -> None:
        self._embed = embedder
        self._query_inflight: dict[
            tuple[uuid.UUID, str, int], asyncio.Task[dict[str, Any]]
        ] = {}

    async def index_row(self, db: AsyncSession, row: Any, *, commit: bool = True) -> None:
        if isinstance(row, Message) and row.source.startswith("brain_"):
            return
        if isinstance(row, Memory) and not _memory_visible(row):
            await db.execute(delete(MemorySearchDocument).where(
                MemorySearchDocument.user_id == row.user_id,
                MemorySearchDocument.source_type == "memory",
                MemorySearchDocument.source_id == str(row.id),
            ))
            if commit:
                await db.commit()
            return
        document = _document(row)
        if isinstance(row, KnowledgeEdge):
            source = await db.get(KnowledgeEntity, row.source_entity_id)
            target = await db.get(KnowledgeEntity, row.target_entity_id)
            if source is not None and target is not None:
                document = SearchDocument(
                    "knowledge_edge",
                    str(row.id),
                    f"{source.name} {row.relation_type} {target.name}",
                    f"{source.name} is {row.relation_type.replace('_', ' ')} {target.name}",
                    {"source_entity_id": str(source.id), "source_name": source.name,
                     "target_entity_id": str(target.id), "target_name": target.name,
                     "weight": float(row.weight or 0)},
                    _utc(row.updated_at),
                )
        vector = await self._embed(f"{document.title}\n{document.content}")
        buckets = _lsh_buckets(vector)
        result = await db.execute(select(MemorySearchDocument).where(
            MemorySearchDocument.user_id == row.user_id,
            MemorySearchDocument.source_type == document.source_type,
            MemorySearchDocument.source_id == document.source_id,
        ))
        indexed = result.scalar_one_or_none()
        if indexed is None:
            indexed = MemorySearchDocument(
                user_id=row.user_id, source_type=document.source_type,
                source_id=document.source_id, title=document.title, content=document.content,
                metadata_json=document.metadata, embedding=vector,
                bucket_0=buckets[0], bucket_1=buckets[1], bucket_2=buckets[2], bucket_3=buckets[3],
                source_updated_at=document.updated_at,
            )
            db.add(indexed)
        else:
            indexed.title = document.title
            indexed.content = document.content
            indexed.metadata_json = document.metadata
            indexed.embedding = vector
            indexed.bucket_0, indexed.bucket_1, indexed.bucket_2, indexed.bucket_3 = buckets
            indexed.source_updated_at = document.updated_at
            indexed.indexed_at = datetime.now(UTC)
        if commit:
            await db.commit()

    async def delete_source(self, db: AsyncSession, user_id: uuid.UUID, source_type: str, source_id: str) -> None:
        await db.execute(delete(MemorySearchDocument).where(
            MemorySearchDocument.user_id == user_id,
            MemorySearchDocument.source_type == source_type,
            MemorySearchDocument.source_id == str(source_id),
        ))
        await db.commit()

    async def delete_domain(self, db: AsyncSession, user_id: uuid.UUID, source_type: str) -> None:
        await db.execute(delete(MemorySearchDocument).where(
            MemorySearchDocument.user_id == user_id,
            MemorySearchDocument.source_type == source_type,
        ))
        await db.commit()

    async def backfill_user(self, db: AsyncSession, user_id: uuid.UUID, *, force: bool = False) -> int:
        """Build a user's legacy index outside the latency-sensitive turn path."""
        status = await db.get(MemoryIndexStatus, user_id)
        if not force and status is not None and status.schema_version == INDEX_SCHEMA_VERSION:
            return 0
        indexed_count = 0
        sources: tuple[tuple[type, Any], ...] = (
            (Memory, Memory.created_at), (BusinessProject, BusinessProject.created_at),
            (BusinessProjectEvent, BusinessProjectEvent.created_at),
            (KnowledgeEntity, KnowledgeEntity.created_at), (KnowledgeEdge, KnowledgeEdge.created_at),
            (Goal, Goal.created_at), (Task, Task.created_at), (Reminder, Reminder.created_at),
            (CalendarEventCache, CalendarEventCache.imported_at), (TodayItem, TodayItem.created_at),
        )
        for model, order_column in sources:
            rows = (await db.execute(select(model).where(model.user_id == user_id).order_by(order_column))).scalars().all()
            for row in rows:
                if isinstance(row, Memory) and not _memory_visible(row):
                    continue
                await self.index_row(db, row, commit=False)
                indexed_count += 1
        recent = (await db.execute(
            select(Message).where(
                Message.user_id == user_id,
                ~Message.source.startswith("brain_"),
            ).order_by(Message.created_at.desc()).limit(100)
        )).scalars().all()
        for row in recent:
            await self.index_row(db, row, commit=False)
            indexed_count += 1
        if status is None:
            db.add(MemoryIndexStatus(user_id=user_id, schema_version=INDEX_SCHEMA_VERSION))
        else:
            status.schema_version = INDEX_SCHEMA_VERSION
            status.completed_at = datetime.now(UTC)
        await db.commit()
        return indexed_count

    async def retrieve_query(self, db: AsyncSession, user_id: uuid.UUID, query: str, *, limit: int = 16) -> dict[str, Any]:
        """Coalesce identical concurrent retrievals to avoid a thundering herd."""
        dialect = db.bind.dialect.name if db.bind is not None else ""
        if dialect == "postgresql":
            return await self._retrieve_query_uncached(
                db, user_id, query, limit=limit
            )
        key = (user_id, query.strip(), limit)
        task = self._query_inflight.get(key)
        if task is None:
            task = asyncio.create_task(
                self._retrieve_query_uncached(db, user_id, query, limit=limit)
            )
            self._query_inflight[key] = task
        try:
            return await asyncio.shield(task)
        finally:
            if task.done() and self._query_inflight.get(key) is task:
                self._query_inflight.pop(key, None)

    async def _retrieve_query_uncached(self, db: AsyncSession, user_id: uuid.UUID, query: str, *, limit: int = 16) -> dict[str, Any]:
        """Stage 2: bounded vector retrieval after the final transcript."""
        started = time.monotonic()
        vector = await self._embed(query)
        dialect = db.bind.dialect.name if db.bind is not None else ""
        if dialect == "postgresql":
            vector_literal = "[" + ",".join(f"{value:.8f}" for value in vector) + "]"
            statement = text(
                "SELECT id FROM memory_search_documents "
                "WHERE user_id = :user_id ORDER BY embedding <=> CAST(:embedding AS vector) LIMIT :candidate_limit"
            )
            ids = [row[0] for row in (await db.execute(statement, {"user_id": user_id, "embedding": vector_literal, "candidate_limit": max(limit * 4, 40)})).all()]
            candidates = (await db.execute(select(MemorySearchDocument).where(MemorySearchDocument.id.in_(ids)))).scalars().all() if ids else []
            candidate_vectors = [row.embedding for row in candidates]
        else:
            buckets = await asyncio.to_thread(_lsh_buckets, vector)
            candidate_rows = (await db.execute(
                select(
                    MemorySearchDocument.id,
                    cast(MemorySearchDocument.embedding, Text),
                ).where(
                    MemorySearchDocument.user_id == user_id,
                    or_(
                        MemorySearchDocument.bucket_0 == buckets[0], MemorySearchDocument.bucket_1 == buckets[1],
                        MemorySearchDocument.bucket_2 == buckets[2], MemorySearchDocument.bucket_3 == buckets[3],
                    ),
                ).order_by(MemorySearchDocument.source_updated_at.desc()).limit(SEARCH_CANDIDATE_LIMIT)
            )).all()
            if not candidate_rows:
                candidate_rows = (await db.execute(
                    select(
                        MemorySearchDocument.id,
                        cast(MemorySearchDocument.embedding, Text),
                    ).where(MemorySearchDocument.user_id == user_id)
                    .order_by(MemorySearchDocument.source_updated_at.desc()).limit(SEARCH_CANDIDATE_LIMIT)
                )).all()
            candidate_vectors = [row[1] for row in candidate_rows]
            ranked_indexes = await asyncio.to_thread(
                _rank_candidate_indexes,
                vector,
                candidate_vectors,
                min(len(candidate_rows), max(limit * 4, 40)),
            )
            ranked_ids = [candidate_rows[index][0] for index in ranked_indexes]
            rows = (await db.execute(
                select(MemorySearchDocument).where(
                    MemorySearchDocument.id.in_(ranked_ids)
                )
            )).scalars().all() if ranked_ids else []
            by_id = {row.id: row for row in rows}
            ranked = [by_id[row_id] for row_id in ranked_ids if row_id in by_id]
            candidates = candidate_rows

        if dialect == "postgresql":
            candidate_vectors = [row.embedding for row in candidates]
            ranked_indexes = await asyncio.to_thread(
                _rank_candidate_indexes,
                vector,
                candidate_vectors,
                len(candidates),
            )
            ranked = [candidates[index] for index in ranked_indexes]
        now = datetime.now(UTC)
        ranked = [
            row for row in ranked if _indexed_document_visible(row, now=now)
        ][:limit]
        items = [{
            "id": row.source_id, "source_type": row.source_type, "title": row.title,
            "content": row.content, **dict(row.metadata_json or {}),
        } for row in ranked]
        return {"items": items, "metrics": {"query_retrieval_ms": int((time.monotonic() - started) * 1000), "candidate_count": len(candidates), "result_count": len(items), "backend": "pgvector" if dialect == "postgresql" else "lsh_cosine"}}

    async def retrieve_stable(self, db: AsyncSession, user: User, *, conversation_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Stage 1: stable, bounded context while speech is in progress."""
        started = time.monotonic()
        local_day = user_local_today(user.timezone)
        try:
            timezone = ZoneInfo(user.timezone or "UTC")
        except ZoneInfoNotFoundError:
            timezone = ZoneInfo("UTC")
        day_start = datetime.combine(local_day, day_time.min, tzinfo=timezone).astimezone(UTC)
        day_end = day_start + timedelta(days=1)

        profile = (await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))).scalar_one_or_none()
        projects = (await db.execute(select(BusinessProject).where(BusinessProject.user_id == user.id, BusinessProject.status != "archived").order_by(BusinessProject.updated_at.desc()).limit(6))).scalars().all()
        people = (await db.execute(select(KnowledgeEntity).where(KnowledgeEntity.user_id == user.id, KnowledgeEntity.entity_type.in_(("person", "relationship"))).order_by(KnowledgeEntity.updated_at.desc()).limit(10))).scalars().all()
        goals = (await db.execute(select(Goal).where(Goal.user_id == user.id, Goal.status.in_(("active", "paused"))).order_by(Goal.updated_at.desc()).limit(8))).scalars().all()
        tasks = (await db.execute(select(Task).where(Task.user_id == user.id, Task.status.not_in(("done", "cancelled"))).order_by(Task.due_at.asc().nullslast(), Task.updated_at.desc()).limit(12))).scalars().all()
        reminders = (await db.execute(select(Reminder).where(Reminder.user_id == user.id, Reminder.status == "scheduled").order_by(Reminder.remind_at).limit(8))).scalars().all()
        calendar = (await db.execute(select(CalendarEventCache).where(CalendarEventCache.user_id == user.id, CalendarEventCache.starts_at >= day_start, CalendarEventCache.starts_at < day_end).order_by(CalendarEventCache.starts_at).limit(12))).scalars().all()
        today = (await db.execute(select(TodayItem).where(TodayItem.user_id == user.id, or_(TodayItem.start_time.between(day_start, day_end), TodayItem.due_at.between(day_start, day_end))).order_by(TodayItem.start_time.asc().nullslast()).limit(16))).scalars().all()
        messages_query = select(Message).where(Message.user_id == user.id)
        messages_query = messages_query.where(~Message.source.startswith("brain_"))
        if conversation_id is not None:
            messages_query = messages_query.where(Message.conversation_id == conversation_id)
        messages = (await db.execute(messages_query.order_by(Message.created_at.desc()).limit(8))).scalars().all()
        now = datetime.now(UTC)
        memories = (await db.execute(select(Memory).where(
            Memory.user_id == user.id,
            Memory.paused.is_(False),
            Memory.user_approved.is_(True),
            Memory.approval_status == "approved",
            or_(
                Memory.memory_scope != "temporary",
                Memory.expires_at.is_(None),
                Memory.expires_at > now,
            ),
        ).order_by(Memory.importance.desc(), Memory.updated_at.desc()).limit(6))).scalars().all()

        return {
            "profile_summary": (profile.summary if profile else None) or user.about_me or "",
            "projects": [self._item(row) for row in projects], "people": [self._item(row) for row in people],
            "goals": [self._item(row) for row in goals], "tasks": [self._item(row) for row in tasks],
            "reminders": [self._item(row) for row in reminders], "calendar": [self._item(row) for row in calendar],
            "today": [self._item(row) for row in today], "recent_discussions": [self._item(row) for row in reversed(messages)],
            "long_term_memory": [self._item(row) for row in memories],
            "metrics": {"stable_retrieval_ms": int((time.monotonic() - started) * 1000)},
        }

    @staticmethod
    def _item(row: Any) -> dict[str, Any]:
        doc = _document(row)
        return {"id": doc.source_id, "source_type": doc.source_type, "title": doc.title, "content": doc.content, **doc.metadata}

    @staticmethod
    def merge(stable: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
        """Deduplicate both retrieval stages into the legacy context contract."""
        merged = {
            "tasks": list(stable.get("tasks", [])) + list(stable.get("today", [])) + list(stable.get("calendar", [])) + list(stable.get("reminders", [])),
            "memories": list(stable.get("long_term_memory", [])) + list(stable.get("recent_discussions", [])),
            "goals": list(stable.get("goals", [])), "projects": list(stable.get("projects", [])),
            "people": list(stable.get("people", [])),
        }
        destination = {"task": "tasks", "today": "tasks", "calendar": "tasks", "reminder": "tasks", "goal": "goals", "project": "projects", "person": "people"}
        for item in query.get("items", []):
            key = destination.get(str(item.get("source_type")), "memories")
            identity = (item.get("source_type"), str(item.get("id")))
            existing = {(entry.get("source_type"), str(entry.get("id"))) for entry in merged[key]}
            if identity not in existing:
                merged[key].append(item)
        merged["metrics"] = {**dict(stable.get("metrics") or {}), **dict(query.get("metrics") or {})}
        return merged


memory_manager = MemoryManager()
