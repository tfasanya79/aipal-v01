import json
import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.types import UserDefinedType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

try:  # pragma: no cover - optional dependency for production pgvector support
    from pgvector.sqlalchemy import Vector as PGVector  # type: ignore
except Exception:  # pragma: no cover - sqlite/test fallback
    PGVector = None


class Vector1536(UserDefinedType):
    """Portable vector column.

    In PostgreSQL this compiles to `vector(1536)`. On SQLite it remains a
    permissive custom type, while the bind/result processors serialize values as
    JSON so tests can round-trip embeddings without pgvector installed.
    """

    cache_ok = True

    def get_col_spec(self, **kw):
        return "vector(1536)"

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                return value
            return json.dumps(list(value))

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    return value
            return value

        return process


EmbeddingVector = PGVector(1536) if PGVector is not None else Vector1536()


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    wake_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    about_me: Mapped[str | None] = mapped_column(Text, nullable=True)
    morning_brief_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    evening_recap_at: Mapped[time | None] = mapped_column(Time, nullable=True)
    checkin_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="user")
    sessions: Mapped[list["LiveSession"]] = relationship(back_populates="user")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user")
    profile_row: Mapped["UserProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="planned")
    source: Mapped[str] = mapped_column(String(32), default="text")
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    parent_task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="tasks")
    goal: Mapped["Goal | None"] = relationship(back_populates="tasks")
    subtasks: Mapped[list["Task"]] = relationship("Task", back_populates="parent", foreign_keys=[parent_task_id])
    parent: Mapped["Task | None"] = relationship("Task", back_populates="subtasks", remote_side=[id], foreign_keys=[parent_task_id])


class LiveSession(Base):
    __tablename__ = "live_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    state: Mapped[str] = mapped_column(String(16), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")


class CalendarEventCache(Base):
    __tablename__ = "calendar_events_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    strengths: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    challenges: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    preferences: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    life_areas: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    current_projects: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    current_goals: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    user: Mapped["User"] = relationship(back_populates="profile_row")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    mode: Mapped[str] = mapped_column(String(32), default="companion")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class ConversationStateRecord(Base):
    """Durable source of truth for the active state of one conversation."""

    __tablename__ = "conversation_states"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    emotion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    life_area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=1)
    confidence: Mapped[float] = mapped_column(default=0.5)
    approval_status: Mapped[str] = mapped_column(String(32), default="approved")
    memory_scope: Mapped[str] = mapped_column(String(32), default="permanent")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suggested_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("memories.id"), nullable=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True
    )
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    follow_up_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entities: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding: Mapped[list[float] | str | None] = mapped_column(EmbeddingVector, nullable=True)
    sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    user_approved: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    source_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MemorySearchDocument(Base):
    """User-scoped semantic projection used by the unified Memory Manager.

    Source tables remain authoritative. This table is a rebuildable search
    index spanning every conversational memory domain.
    """

    __tablename__ = "memory_search_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "source_type", "source_id", name="uq_memory_search_source"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    source_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    embedding: Mapped[list[float] | str] = mapped_column(EmbeddingVector, nullable=False)
    bucket_0: Mapped[str] = mapped_column(String(16), index=True)
    bucket_1: Mapped[str] = mapped_column(String(16), index=True)
    bucket_2: Mapped[str] = mapped_column(String(16), index=True)
    bucket_3: Mapped[str] = mapped_column(String(16), index=True)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    indexed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MemoryIndexStatus(Base):
    """Tracks completion of the one-time legacy-data semantic backfill."""

    __tablename__ = "memory_index_status"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    aliases: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_entities.id"), index=True)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_entities.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(64), index=True)
    weight: Mapped[float] = mapped_column(Numeric(5, 2), default=1)
    evidence_memory_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("memories.id"), nullable=True, index=True)
    evidence_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class MemoryEntityLink(Base):
    __tablename__ = "memory_entity_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    memory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memories.id"), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_entities.id"), index=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Commitment(Base):
    __tablename__ = "commitments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    source_memory_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("memories.id"), nullable=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.8)
    related_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_entities.id"), nullable=True, index=True)
    related_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    related_entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    life_area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    priority: Mapped[str] = mapped_column(String(32), default="medium")
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    tasks: Mapped[list["Task"]] = relationship(back_populates="goal")
    reflections: Mapped[list["Reflection"]] = relationship(back_populates="goal")


class EmotionalState(Base):
    __tablename__ = "emotional_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    emotion: Mapped[str] = mapped_column(String(32))
    intensity: Mapped[int] = mapped_column(Integer, default=1)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CoachDecision(Base):
    __tablename__ = "coach_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    selected_option: Mapped[str | None] = mapped_column(Text, nullable=True)
    framework: Mapped[str] = mapped_column(String(64))
    analysis: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    recommendation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.5)
    status: Mapped[str] = mapped_column(String(32), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ThinkingSession(Base):
    __tablename__ = "thinking_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    framework: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    output: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GrowthPlan(Base):
    __tablename__ = "growth_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    horizon: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    milestones: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    weekly_focus: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    success_metrics: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AccountabilitySnapshot(Base):
    __tablename__ = "accountability_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    goals_summary: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    tasks_summary: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    habits_summary: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    blockers: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Habit(Base):
    __tablename__ = "habits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    life_area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    frequency: Mapped[str] = mapped_column(String(16), default="daily")
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class HabitLog(Base):
    __tablename__ = "habit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    habit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("habits.id"), index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    value: Mapped[int] = mapped_column(Integer, default=1)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Reflection(Base):
    __tablename__ = "reflections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(32))
    wins: Mapped[str | None] = mapped_column(Text, nullable=True)
    challenges: Mapped[str | None] = mapped_column(Text, nullable=True)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    score: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    goal: Mapped["Goal | None"] = relationship(back_populates="reflections")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recurrence_rule: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    participants: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    meeting_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("business_projects.id"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="scheduled", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class MeetingNote(Base):
    __tablename__ = "meeting_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    decisions: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    action_items: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    followups: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class TodayItem(Base):
    __tablename__ = "today_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("goals.id"), nullable=True, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    calendar_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    reminder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reminders.id"), nullable=True, index=True)
    habit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("habits.id"), nullable=True, index=True)
    reflection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reflections.id"), nullable=True, index=True)
    commitment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("commitments.id"), nullable=True, index=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(32), default="aipal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    today_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("today_items.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(32), index=True)
    channel: Mapped[str] = mapped_column(String(32), index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reminder_lead_minutes: Mapped[int] = mapped_column(Integer, default=10)
    meeting_lead_minutes: Mapped[int] = mapped_column(Integer, default=30)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    details: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PlanDraft(Base):
    __tablename__ = "plan_drafts"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class IntegrationToken(Base):
    __tablename__ = "integration_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserCompanionPreference(Base):
    __tablename__ = "user_companion_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, index=True)
    proactive_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    max_proactive_per_day: Mapped[int] = mapped_column(Integer, default=1)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    tone: Mapped[str] = mapped_column(String(32), default="warm")
    humor_level: Mapped[int] = mapped_column(Integer, default=1)
    directness_level: Mapped[int] = mapped_column(Integer, default=5)
    voice_pace: Mapped[str] = mapped_column(String(16), default="normal")
    tts_voice: Mapped[str] = mapped_column(String(64), default="default")
    response_length: Mapped[str] = mapped_column(String(16), default="balanced")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProactivePrompt(Base):
    __tablename__ = "proactive_prompts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    trigger_type: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    trigger_metadata: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class EmotionalPattern(Base):
    __tablename__ = "emotional_patterns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    pattern_type: Mapped[str] = mapped_column(String(64))
    emotion: Mapped[str] = mapped_column(String(32))
    life_area: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.5)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    account_label: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConnectedItem(Base):
    __tablename__ = "connected_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    connected_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("connected_accounts.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    item_type: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255))
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_metadata: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding: Mapped[list[float] | str | None] = mapped_column(EmbeddingVector, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExternalCommitment(Base):
    __tablename__ = "external_commitments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    source_provider: Mapped[str] = mapped_column(String(64), index=True)
    source_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("connected_items.id"), index=True)
    commitment_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    confidence: Mapped[float] = mapped_column(Numeric(5, 2), default=0.5)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ConnectorAuditLog(Base):
    __tablename__ = "connector_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BusinessProject(Base):
    __tablename__ = "business_projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    goals: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    key_people: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    opportunities: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BusinessProjectEvent(Base):
    __tablename__ = "business_project_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("business_projects.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ProjectRoom(Base):
    __tablename__ = "project_rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    business_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_projects.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    goals: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    key_people: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    risks: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    opportunities: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ProjectRoomLink(Base):
    __tablename__ = "project_room_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("project_rooms.id"), index=True)
    linked_type: Mapped[str] = mapped_column(String(64), index=True)
    linked_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    today_item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("today_items.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)
