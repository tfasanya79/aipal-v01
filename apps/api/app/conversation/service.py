"""Small transport-facing facade for the unified conversation orchestrator."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .contracts import (
    ConversationEvent,
    ConversationInput,
    ConversationResult,
    InputModality,
    OrchestrationContext,
)
from .dependencies import get_conversation_orchestrator


def build_conversation_input(
    *,
    user: User,
    text: str,
    modality: InputModality,
    conversation_id: uuid.UUID | None = None,
    turn_id: str | None = None,
    source_context: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ConversationInput:
    return ConversationInput(
        user_id=user.id,
        text=text,
        modality=modality,
        conversation_id=conversation_id or uuid.uuid4(),
        turn_id=turn_id or str(uuid.uuid4()),
        source_context=source_context,
        metadata=metadata or {},
    )


async def run_conversation(
    db: AsyncSession,
    user: User,
    text: str,
    *,
    modality: InputModality,
    conversation_id: uuid.UUID | None = None,
    turn_id: str | None = None,
    source_context: dict[str, Any] | None = None,
) -> ConversationResult:
    request = build_conversation_input(
        user=user,
        text=text,
        modality=modality,
        conversation_id=conversation_id,
        turn_id=turn_id,
        source_context=source_context,
    )
    return await get_conversation_orchestrator().run(
        request,
        OrchestrationContext(db=db, user=user),
    )


async def stream_conversation(
    db: AsyncSession,
    user: User,
    text: str,
    *,
    modality: InputModality,
    conversation_id: uuid.UUID | None = None,
    turn_id: str | None = None,
    source_context: dict[str, Any] | None = None,
    cancel_event: asyncio.Event | None = None,
    preloaded_context: dict[str, Any] | None = None,
) -> AsyncIterator[ConversationEvent]:
    request = build_conversation_input(
        user=user,
        text=text,
        modality=modality,
        conversation_id=conversation_id,
        turn_id=turn_id,
        source_context=source_context,
    )
    context = OrchestrationContext(
        db=db,
        user=user,
        cancel_event=cancel_event,
        preloaded_context=preloaded_context,
    )
    async for event in get_conversation_orchestrator().stream(request, context):
        yield event
