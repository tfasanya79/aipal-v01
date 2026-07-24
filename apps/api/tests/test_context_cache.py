from __future__ import annotations

import uuid

import pytest

from app.db import async_session
from app.models import Conversation, Message
from app.services.companion_orchestrator import _recent_context
from app.services.context_cache import get_context_cache


@pytest.mark.asyncio
async def test_recent_context_is_cached_after_db_lookup():
    user_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    async with async_session() as db:
        conv = Conversation(id=conversation_id, user_id=user_id, mode="companion", title="Cache test")
        db.add(conv)
        db.add(Message(conversation_id=conversation_id, user_id=user_id, role="user", content="Qring context"))
        db.add(Message(conversation_id=conversation_id, user_id=user_id, role="assistant", content="I remember Qring."))
        await db.commit()

        context = await _recent_context(db, user_id, conversation_id)

    assert "Qring context" in context
    cached = await get_context_cache(str(user_id), str(conversation_id))
    assert cached is not None
    assert "Qring context" in cached["recent_context"]
