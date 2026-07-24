"""Typed, durable conversation state and its single persistence manager."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Conversation, ConversationStateRecord
from ..services.context_cache import (
    delete_context_cache,
    get_context_cache,
    set_context_cache,
)
from .contracts import ConversationInput


class ConversationStateConflictError(RuntimeError):
    pass


class ConversationStatus(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    USER_SPEAKING = "user_speaking"
    THINKING = "thinking"
    AI_SPEAKING = "ai_speaking"
    INTERRUPTED = "interrupted"
    COLLECTING_TASK_FIELDS = "collecting_task_fields"
    COLLECTING_MEETING_FIELDS = "collecting_meeting_fields"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    ACTION_COMPLETED = "action_completed"
    ENDED = "ended"
    ERROR = "error"


class Speaker(StrEnum):
    NONE = "none"
    USER = "user"
    AIPAL = "aipal"


class StateReference(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    name: str


class EmotionState(BaseModel):
    model_config = ConfigDict(extra="allow")

    emotion: str = "neutral"
    intensity: int = Field(default=1, ge=0, le=10)
    context: str = ""


class InterruptionState(BaseModel):
    turn_id: str | None = None
    interrupted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    speaker: Speaker = Speaker.USER


class PendingConfirmation(BaseModel):
    confirmation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action_id: str = "legacy-unbound"
    topic_id: str = "legacy-unbound"
    conversation_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    requested_turn_id: str = "legacy-unbound"
    prompt: str
    invalidated_at: datetime | None = None
    invalidation_reason: str | None = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=30)
    )


class PendingAction(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic_id: str | None = None
    originating_turn_id: str | None = None
    state: str
    kind: str
    intent: str
    fields: dict[str, Any] = Field(default_factory=dict)
    missing: str | None = None
    requires_confirmation: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC) + timedelta(minutes=30)
    )


class TopicStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_INFORMATION = "awaiting_information"


class TopicState(BaseModel):
    topic_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    topic_type: str = "general"
    title: str
    active_goal: str | None = None
    status: TopicStatus = TopicStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_turn_id: str | None = None
    language: str = "unknown"
    entities: dict[str, Any] = Field(default_factory=dict)
    pending_action_id: str | None = None
    parent_topic_id: str | None = None
    related_topic_ids: list[str] = Field(default_factory=list)
    resume_count: int = Field(default=0, ge=0)
    summary: str = ""


class ConversationState(BaseModel):
    """Complete active state for one conversation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "2.0"
    conversation_id: uuid.UUID
    user_id: uuid.UUID
    version: int = Field(default=1, ge=1)
    status: ConversationStatus = ConversationStatus.IDLE
    current_topic: str | None = None
    active_topic: TopicState | None = None
    topic_history: list[TopicState] = Field(default_factory=list, max_length=20)
    topic_transition_sequence: int = Field(default=0, ge=0)
    current_goal: StateReference | None = None
    pending_action: PendingAction | None = None
    pending_confirmation: PendingConfirmation | None = None
    current_emotion: EmotionState = Field(default_factory=EmotionState)
    active_project: StateReference | None = None
    current_people: list[StateReference] = Field(default_factory=list)
    current_tools: list[str] = Field(default_factory=list)
    conversation_summary: str = ""
    last_interruption: InterruptionState | None = None
    last_ai_response: str | None = None
    user_intent: str | None = None
    conversation_mode: str = "companion"
    current_turn_id: str | None = None
    last_speaker: Speaker = Speaker.NONE
    currently_speaking: Speaker = Speaker.NONE
    partial_transcript: str | None = None
    partial_confidence: float | None = Field(default=None, ge=0, le=1)
    final_transcript: str | None = None
    final_confidence: float | None = Field(default=None, ge=0, le=1)
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def pending_state_is_consistent(self) -> "ConversationState":
        if self.pending_confirmation is not None and self.pending_action is None:
            raise ValueError("Pending confirmation requires a pending action")
        if (
            self.pending_action is not None
            and self.pending_action.requires_confirmation
            and self.pending_confirmation is None
        ):
            raise ValueError(
                "Confirmable pending action requires confirmation metadata"
            )
        return self


class ConversationStatePatch(BaseModel):
    """Patch contract where omitted means unchanged and explicit null means clear."""

    model_config = ConfigDict(extra="forbid")

    status: ConversationStatus = ConversationStatus.IDLE
    current_topic: str | None = None
    active_topic: TopicState | None = None
    topic_history: list[TopicState] = Field(default_factory=list, max_length=20)
    topic_transition_sequence: int = Field(default=0, ge=0)
    current_goal: StateReference | None = None
    pending_action: PendingAction | None = None
    pending_confirmation: PendingConfirmation | None = None
    current_emotion: EmotionState = Field(default_factory=EmotionState)
    active_project: StateReference | None = None
    current_people: list[StateReference] = Field(default_factory=list)
    current_tools: list[str] = Field(default_factory=list)
    conversation_summary: str = ""
    last_interruption: InterruptionState | None = None
    last_ai_response: str | None = None
    user_intent: str | None = None
    conversation_mode: str = "companion"
    current_turn_id: str | None = None
    last_speaker: Speaker = Speaker.NONE
    currently_speaking: Speaker = Speaker.NONE
    partial_transcript: str | None = None
    partial_confidence: float | None = Field(default=None, ge=0, le=1)
    final_transcript: str | None = None
    final_confidence: float | None = Field(default=None, ge=0, le=1)
    language: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SqlAlchemyConversationStateManager:
    CACHE_PREFIX = "conversation-state:"

    async def load(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        create: bool = True,
        use_cache: bool = True,
        expire_pending: bool = True,
    ) -> ConversationState | None:
        cache_id = self._cache_id(conversation_id)
        if use_cache:
            cached = await get_context_cache(str(user_id), cache_id)
            if cached:
                state = ConversationState.model_validate(cached)
                if expire_pending and self._pending_expired(state):
                    return await self._clear_expired_pending(db, state=state)
                return state

        record = await self._record(
            db, user_id=user_id, conversation_id=conversation_id
        )
        if record is None:
            if not create:
                return None
            state = await self._create(
                db, user_id=user_id, conversation_id=conversation_id
            )
        else:
            state = self._from_record(record)
        if expire_pending and self._pending_expired(state):
            return await self._clear_expired_pending(db, state=state)
        await self._cache(state)
        return state

    async def patch(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        patch: ConversationStatePatch,
        expected_version: int | None = None,
    ) -> ConversationState:
        for attempt in range(3):
            current = await self.load(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                create=True,
                # The cached snapshot is safe as an optimistic first attempt:
                # the SQL UPDATE still compares its version atomically. A
                # cross-process stale snapshot produces rowcount=0, is evicted,
                # and retries from the durable row below. This removes one DB
                # round trip from the normal mutation path without weakening
                # conflict detection.
                use_cache=expected_version is None and attempt == 0,
                expire_pending=False,
            )
            assert current is not None
            if expected_version is not None and current.version != expected_version:
                raise ConversationStateConflictError(
                    f"Expected conversation state version {expected_version}, found {current.version}"
                )
            values = current.model_dump()
            for field in patch.model_fields_set:
                values[field] = getattr(patch, field)
            values["version"] = current.version + 1
            values["updated_at"] = datetime.now(UTC)
            candidate = ConversationState.model_validate(values)
            result = await db.execute(
                update(ConversationStateRecord)
                .where(
                    ConversationStateRecord.conversation_id == conversation_id,
                    ConversationStateRecord.user_id == user_id,
                    ConversationStateRecord.version == current.version,
                )
                .values(
                    state_json=self._state_json(candidate),
                    version=candidate.version,
                    updated_at=candidate.updated_at,
                )
            )
            if result.rowcount == 1:
                await db.commit()
                await self._cache(candidate)
                return candidate
            await db.rollback()
            await delete_context_cache(str(user_id), self._cache_id(conversation_id))
            if expected_version is not None or attempt == 2:
                raise ConversationStateConflictError(
                    "Conversation state changed concurrently"
                )
        raise ConversationStateConflictError("Conversation state update failed")

    async def begin_turn(
        self,
        db: AsyncSession,
        request: ConversationInput,
    ) -> ConversationState | None:
        if request.conversation_id is None:
            return None
        stt = (request.source_context or {}).get("stt") or {}
        current = await self.load(
            db,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            create=True,
            use_cache=False,
        )
        assert current is not None
        from .topic_transition import topic_transition_service

        language = str(stt.get("stt_language") or current.language or "unknown")
        transition = topic_transition_service.classify(
            state=current,
            utterance=request.text,
            turn_id=request.turn_id,
            language=language,
        )
        policy = topic_transition_service.apply_policy(
            current, transition, request.text, language
        )
        metadata = dict(current.metadata)
        metadata["topic_transition"] = policy.decision.model_dump(mode="json")
        processed_turns = list(metadata.get("processed_topic_turn_ids") or [])
        processed_turns.append(request.turn_id)
        metadata["processed_topic_turn_ids"] = list(
            dict.fromkeys(processed_turns)
        )[-100:]
        patch_values: dict[str, Any] = {
            "status": ConversationStatus.THINKING,
            "current_topic": policy.active_topic.title,
            "active_topic": policy.active_topic,
            "topic_history": list(policy.topic_history),
            "topic_transition_sequence": policy.decision.transition_sequence,
            "current_turn_id": request.turn_id,
            "last_speaker": Speaker.USER,
            "currently_speaking": Speaker.NONE,
            "partial_transcript": None,
            "partial_confidence": None,
            "final_transcript": request.text or None,
            "final_confidence": self._optional_probability(stt.get("stt_confidence")),
            "language": language,
            "metadata": metadata,
        }
        if policy.pending_action is not current.pending_action or policy.clear_pending_confirmation:
            patch_values["pending_action"] = policy.pending_action
            patch_values["pending_confirmation"] = None
        return await self.patch(
            db,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            patch=ConversationStatePatch.model_validate(patch_values),
            expected_version=current.version,
        )

    async def complete_turn(
        self,
        db: AsyncSession,
        request: ConversationInput,
        terminal: dict[str, Any],
    ) -> ConversationState:
        conversation_id = self._terminal_conversation_id(request, terminal)
        current = await self.load(
            db,
            user_id=request.user_id,
            conversation_id=conversation_id,
            create=True,
            use_cache=False,
        )
        assert current is not None
        reply = str(terminal.get("reply") or "").strip()
        requires_confirmation = bool(terminal.get("requires_confirmation"))
        transition = dict(current.metadata.get("topic_transition") or {})
        transition_class = str(transition.get("classification") or "")
        pending_action = current.pending_action
        if requires_confirmation:
            pending_action = self._pending_from_terminal(terminal)
            pending_action = pending_action.model_copy(
                update={
                    "topic_id": current.active_topic.topic_id if current.active_topic else None,
                    "originating_turn_id": request.turn_id,
                }
            )
        elif not transition_class or transition_class in {
            "cancel_active_request",
            "reject_pending_action",
            "new_unrelated_topic",
        }:
            pending_action = None
        pending_confirmation = (
            PendingConfirmation(
                action_id=pending_action.action_id,
                topic_id=pending_action.topic_id or "unbound",
                conversation_id=conversation_id,
                user_id=request.user_id,
                requested_turn_id=request.turn_id,
                prompt=str(terminal.get("confirmation_prompt") or "Please confirm.")
            )
            if requires_confirmation and pending_action is not None
            else current.pending_confirmation if pending_action is not None else None
        )
        source_context = request.source_context or {}
        stt = source_context.get("stt") or {}
        active_topic = current.active_topic
        if active_topic is not None:
            active_topic = active_topic.model_copy(
                update={
                    "pending_action_id": pending_action.action_id
                    if pending_action is not None
                    else None,
                    "status": TopicStatus.AWAITING_CONFIRMATION
                    if requires_confirmation
                    else active_topic.status,
                    "updated_at": datetime.now(UTC),
                }
            )
        patch_data: dict[str, Any] = {
            "status": ConversationStatus.AWAITING_CONFIRMATION
            if requires_confirmation
            else ConversationStatus.LISTENING,
            "current_topic": current.active_topic.title if current.active_topic else current.current_topic,
            "active_topic": active_topic,
            "pending_action": pending_action,
            "pending_confirmation": pending_confirmation,
            "current_emotion": EmotionState.model_validate(
                terminal.get("emotion") or {}
            ),
            "current_tools": self._tools(terminal),
            "conversation_summary": self._rolling_summary(
                current.conversation_summary, request.text, reply
            ),
            "last_ai_response": reply or None,
            "user_intent": str(
                terminal.get("intent") or terminal.get("mode") or "general_conversation"
            ),
            "conversation_mode": str(terminal.get("mode") or current.conversation_mode),
            "current_turn_id": None,
            "last_speaker": Speaker.AIPAL if reply else Speaker.USER,
            "currently_speaking": Speaker.NONE,
            "partial_transcript": None,
            "partial_confidence": None,
            "final_transcript": request.text or None,
            "final_confidence": self._optional_probability(stt.get("stt_confidence")),
            "language": str(stt.get("stt_language") or current.language or "unknown"),
        }
        if self._reference(source_context, "goal") is not None:
            patch_data["current_goal"] = self._reference(source_context, "goal")
        if self._reference(source_context, "project") is not None:
            patch_data["active_project"] = self._reference(source_context, "project")
        if "people" in source_context:
            patch_data["current_people"] = self._references(
                source_context.get("people")
            )
        patch = ConversationStatePatch.model_validate(patch_data)
        return await self.patch(
            db,
            user_id=request.user_id,
            conversation_id=conversation_id,
            patch=patch,
        )

    async def record_interruption(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        turn_id: str | None,
    ) -> ConversationState:
        return await self.patch(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                status=ConversationStatus.INTERRUPTED,
                last_interruption=InterruptionState(turn_id=turn_id),
                current_turn_id=None,
                currently_speaking=Speaker.USER,
                last_speaker=Speaker.USER,
            ),
        )

    async def cancel_turn(
        self,
        db: AsyncSession,
        request: ConversationInput,
    ) -> ConversationState | None:
        if request.conversation_id is None:
            return None
        return await self.record_interruption(
            db,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
        )

    async def fail_turn(
        self,
        db: AsyncSession,
        request: ConversationInput,
        *,
        reason: str,
    ) -> ConversationState | None:
        if request.conversation_id is None:
            return None
        current = await self.load(
            db,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            create=True,
            use_cache=False,
        )
        assert current is not None
        metadata = dict(current.metadata)
        metadata["last_error"] = reason
        return await self.patch(
            db,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            patch=ConversationStatePatch(
                status=ConversationStatus.ERROR,
                current_turn_id=None,
                currently_speaking=Speaker.NONE,
                metadata=metadata,
            ),
        )

    async def end(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationState:
        return await self.patch(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                status=ConversationStatus.ENDED,
                current_turn_id=None,
                currently_speaking=Speaker.NONE,
            ),
        )

    async def resume(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationState:
        current = await self.load(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            create=True,
            use_cache=False,
        )
        assert current is not None
        status = ConversationStatus.LISTENING
        if current.pending_action is not None:
            try:
                status = ConversationStatus(current.pending_action.state)
            except ValueError:
                status = (
                    ConversationStatus.AWAITING_CONFIRMATION
                    if current.pending_action.requires_confirmation
                    else ConversationStatus.LISTENING
                )
        return await self.patch(
            db,
            user_id=user_id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                status=status,
                current_turn_id=None,
                currently_speaking=Speaker.NONE,
            ),
        )

    async def forget(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> None:
        await db.execute(
            delete(ConversationStateRecord).where(
                ConversationStateRecord.conversation_id == conversation_id,
                ConversationStateRecord.user_id == user_id,
            )
        )
        await delete_context_cache(str(user_id), self._cache_id(conversation_id))

    async def _create(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationState:
        conversation = await db.get(Conversation, conversation_id)
        if conversation is not None and conversation.user_id != user_id:
            raise ValueError("Conversation does not belong to authenticated user")
        if conversation is None:
            db.add(
                Conversation(
                    id=conversation_id,
                    user_id=user_id,
                    mode="companion",
                    title="Conversation",
                )
            )
        state = ConversationState(conversation_id=conversation_id, user_id=user_id)
        db.add(
            ConversationStateRecord(
                conversation_id=conversation_id,
                user_id=user_id,
                state_json=self._state_json(state),
                version=state.version,
                created_at=state.created_at,
                updated_at=state.updated_at,
            )
        )
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            record = await self._record(
                db, user_id=user_id, conversation_id=conversation_id
            )
            if record is None:
                raise
            state = self._from_record(record)
        await self._cache(state)
        return state

    async def _record(
        self,
        db: AsyncSession,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
    ) -> ConversationStateRecord | None:
        return (
            await db.execute(
                select(ConversationStateRecord).where(
                    ConversationStateRecord.conversation_id == conversation_id,
                    ConversationStateRecord.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _from_record(record: ConversationStateRecord) -> ConversationState:
        payload = dict(record.state_json or {})
        payload.update(
            conversation_id=record.conversation_id,
            user_id=record.user_id,
            version=record.version,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
        return ConversationState.model_validate(payload)

    @staticmethod
    def _state_json(state: ConversationState) -> dict[str, Any]:
        payload = state.model_dump(mode="json")
        for field in (
            "conversation_id",
            "user_id",
            "version",
            "created_at",
            "updated_at",
        ):
            payload.pop(field, None)
        return payload

    async def _cache(self, state: ConversationState) -> None:
        await set_context_cache(
            str(state.user_id),
            self._cache_id(state.conversation_id),
            state.model_dump(mode="json"),
        )

    async def _clear_expired_pending(
        self,
        db: AsyncSession,
        *,
        state: ConversationState,
    ) -> ConversationState:
        patch = ConversationStatePatch(
            pending_action=None,
            pending_confirmation=None,
            status=ConversationStatus.LISTENING,
        )
        try:
            return await self.patch(
                db,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                patch=patch,
                expected_version=state.version,
            )
        except ConversationStateConflictError:
            await delete_context_cache(
                str(state.user_id), self._cache_id(state.conversation_id)
            )
            current = await self.load(
                db,
                user_id=state.user_id,
                conversation_id=state.conversation_id,
                use_cache=False,
                expire_pending=False,
            )
            assert current is not None
            if not self._pending_expired(current):
                return current
            return await self.patch(
                db,
                user_id=current.user_id,
                conversation_id=current.conversation_id,
                patch=patch,
            )

    @classmethod
    def _cache_id(cls, conversation_id: uuid.UUID) -> str:
        return f"{cls.CACHE_PREFIX}{conversation_id}"

    @staticmethod
    def _pending_expired(state: ConversationState) -> bool:
        pending = state.pending_action
        if pending is None:
            return False
        expirations = [pending.expires_at]
        if state.pending_confirmation is not None:
            expirations.append(state.pending_confirmation.expires_at)
        expires_at = min(expirations)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= datetime.now(UTC)

    @staticmethod
    def _terminal_conversation_id(
        request: ConversationInput, terminal: dict[str, Any]
    ) -> uuid.UUID:
        raw = terminal.get("conversation_id") or request.conversation_id
        if raw is None:
            raise ValueError(
                "Terminal conversation result did not include a conversation ID"
            )
        return uuid.UUID(str(raw))

    @staticmethod
    def _pending_from_terminal(terminal: dict[str, Any]) -> PendingAction:
        explicit = terminal.get("pending_action")
        if isinstance(explicit, dict):
            return PendingAction.model_validate(explicit)
        raw_draft = terminal.get("plan_draft")
        if hasattr(raw_draft, "model_dump"):
            raw_draft = raw_draft.model_dump(mode="json")
        return PendingAction(
            state="awaiting_confirmation",
            kind=str(terminal.get("mode") or "action"),
            intent=str(terminal.get("intent") or "confirm_action"),
            fields={"plan_draft": raw_draft} if raw_draft else {},
            requires_confirmation=True,
        )

    @staticmethod
    def _rolling_summary(previous: str, user_text: str, reply: str) -> str:
        addition = f"User: {user_text.strip()}\nAiPal: {reply.strip()}".strip()
        return f"{previous.strip()}\n{addition}".strip()[-4000:]

    @staticmethod
    def _reference(context: dict[str, Any], prefix: str) -> StateReference | None:
        raw = context.get(prefix)
        if isinstance(raw, dict) and raw.get("name"):
            return StateReference.model_validate(raw)
        name = context.get(f"{prefix}_name")
        identifier = context.get(f"{prefix}_id")
        if name:
            return StateReference(
                id=str(identifier) if identifier else None, name=str(name)
            )
        return None

    @staticmethod
    def _references(raw: Any) -> list[StateReference]:
        if not isinstance(raw, list):
            return []
        references = []
        for item in raw:
            if isinstance(item, dict) and item.get("name"):
                references.append(StateReference.model_validate(item))
            elif isinstance(item, str) and item.strip():
                references.append(StateReference(name=item.strip()))
        return references

    @staticmethod
    def _tools(terminal: dict[str, Any]) -> list[str]:
        values = terminal.get("tool_actions") or []
        tools = [
            str(item.get("type") or item.get("label"))
            for item in values
            if isinstance(item, dict)
        ]
        if terminal.get("tool"):
            tools.append(str(terminal["tool"]))
        return list(dict.fromkeys(tool for tool in tools if tool))

    @staticmethod
    def _optional_probability(value: Any) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))


conversation_state_manager = SqlAlchemyConversationStateManager()
