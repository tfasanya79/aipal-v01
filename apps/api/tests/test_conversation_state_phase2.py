from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from starlette.testclient import TestClient

from app.auth import create_access_token
from app.conversation.state import (
    ConversationStateConflictError,
    ConversationStatePatch,
    ConversationStatus,
    PendingAction,
    PendingConfirmation,
    StateReference,
    conversation_state_manager,
)
from app.conversation.contracts import ConversationInput, InputModality
from app.conversation.contracts import OrchestrationContext
from app.conversation.orchestrator import ConversationOrchestrator
from app.db import async_session
from app.main import app
from app.models import ConversationStateRecord, User
from app.services.context_cache import delete_context_cache
from app.services import context_cache
from app.services.conversation_state_manager import (
    get_voice_session_state,
    mark_interrupted,
    update_voice_session_state,
)


async def _user(email: str) -> User:
    async with async_session() as db:
        user = User(email=email, timezone="UTC")
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


async def _authed_client(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    registration = await client.post("/api/v2/auth/register", json={"email": email})
    verification = await client.post(
        "/api/v2/auth/verify",
        json={"token": registration.json()["dev_token"]},
    )
    return (
        client,
        {"Authorization": f"Bearer {verification.json()['access_token']}"},
        uuid.UUID(verification.json()["user_id"]),
    )


def _response(reply: str = "I am with you.", *, confirmation: bool = False) -> dict:
    return {
        "reply": reply,
        "mode": "companion",
        "emotion": {"emotion": "calm", "intensity": 2, "context": "Grounded."},
        "suggested_actions": [],
        "should_create_task": False,
        "memory_suggestions": [],
        "context_items_used": [],
        "requires_confirmation": confirmation,
        "confirmation_prompt": "Should I save it?" if confirmation else None,
    }


@pytest.mark.asyncio
async def test_state_survives_cache_loss_and_reconnect():
    user = await _user("phase2-reconnect@example.com")
    conversation_id = uuid.uuid4()
    async with async_session() as db:
        state = await conversation_state_manager.patch(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                current_topic="Qring launch",
                current_goal=StateReference(id="goal-1", name="Launch Qring"),
                conversation_summary="We agreed on the launch sequence.",
            ),
        )
    await delete_context_cache(str(user.id), conversation_state_manager._cache_id(conversation_id))

    async with async_session() as db:
        restored = await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )

    assert restored is not None
    assert restored.current_topic == "Qring launch"
    assert restored.current_goal and restored.current_goal.name == "Launch Qring"
    assert restored.conversation_summary == "We agreed on the launch sequence."
    assert restored.version == state.version


@pytest.mark.asyncio
async def test_disconnect_and_resume_preserve_valid_pending_confirmation():
    user = await _user("phase2-pending-reconnect@example.com")
    conversation_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    async with async_session() as db:
        await conversation_state_manager.patch(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                status=ConversationStatus.AWAITING_CONFIRMATION,
                current_turn_id="finished-turn",
                pending_action=PendingAction(
                    state="awaiting_confirmation",
                    kind="task",
                    intent="create_task",
                    fields={"title": "Call Tobi"},
                    requires_confirmation=True,
                    expires_at=expires_at,
                ),
                pending_confirmation=PendingConfirmation(
                    prompt="Should I create the task?",
                    expires_at=expires_at,
                ),
            ),
        )
        ended = await conversation_state_manager.end(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
        resumed = await conversation_state_manager.resume(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )

    assert ended.status == ConversationStatus.ENDED
    assert ended.current_turn_id is None
    assert ended.pending_action is not None
    assert ended.pending_confirmation is not None
    assert resumed.status == ConversationStatus.AWAITING_CONFIRMATION
    assert resumed.current_turn_id is None
    assert resumed.pending_action and resumed.pending_action.fields["title"] == "Call Tobi"
    assert resumed.pending_confirmation is not None


@pytest.mark.asyncio
async def test_explicit_null_clears_pending_state_instead_of_being_ignored():
    user = await _user("phase2-clear@example.com")
    conversation_id = uuid.uuid4()
    await update_voice_session_state(
        str(user.id),
        str(conversation_id),
        pending_action={
            "state": "awaiting_confirmation",
            "kind": "task",
            "intent": "task_confirmation",
            "fields": {"title": "Call Tobi"},
            "requires_confirmation": True,
        },
    )
    cleared = await update_voice_session_state(
        str(user.id),
        str(conversation_id),
        pending_action=None,
        current_turn_id=None,
    )

    assert cleared["pending_action"] is None
    assert cleared["pending_confirmation"] is None
    assert cleared["current_turn_id"] is None


@pytest.mark.asyncio
async def test_expired_pending_action_is_cleared_on_load():
    user = await _user("phase2-expiry@example.com")
    conversation_id = uuid.uuid4()
    expired = datetime.now(UTC) - timedelta(seconds=1)
    async with async_session() as db:
        await conversation_state_manager.patch(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(
                status=ConversationStatus.AWAITING_CONFIRMATION,
                pending_action=PendingAction(
                    state="awaiting_confirmation",
                    kind="task",
                    intent="task_confirmation",
                    requires_confirmation=True,
                    expires_at=expired,
                ),
                pending_confirmation=PendingConfirmation(
                    prompt="Save it?",
                    expires_at=expired,
                ),
            ),
        )
    await delete_context_cache(str(user.id), conversation_state_manager._cache_id(conversation_id))

    async with async_session() as db:
        state = await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )

    assert state is not None
    assert state.pending_action is None
    assert state.pending_confirmation is None
    assert state.status == ConversationStatus.LISTENING


@pytest.mark.asyncio
async def test_terminal_turn_replaces_then_clears_pending_confirmation():
    user = await _user("phase2-terminal-pending@example.com")
    conversation_id = uuid.uuid4()
    request = ConversationInput(
        user_id=user.id,
        conversation_id=conversation_id,
        modality=InputModality.TEXT,
        text="Draft a task",
    )
    async with async_session() as db:
        pending = await conversation_state_manager.complete_turn(
            db,
            request,
            {
                "reply": "Should I save it?",
                "mode": "assistant",
                "emotion": {"emotion": "neutral", "intensity": 1},
                "requires_confirmation": True,
                "confirmation_prompt": "Should I save it?",
                "conversation_id": str(conversation_id),
                "plan_draft": {"proposed_tasks": [{"title": "Draft a task"}]},
            },
        )
        cleared = await conversation_state_manager.complete_turn(
            db,
            request.model_copy(update={"text": "No, discard it"}),
            {
                "reply": "Okay, I discarded it.",
                "mode": "assistant",
                "emotion": {"emotion": "neutral", "intensity": 1},
                "requires_confirmation": False,
                "conversation_id": str(conversation_id),
            },
        )

    assert pending.pending_action is not None
    assert pending.pending_confirmation is not None
    assert pending.status == ConversationStatus.AWAITING_CONFIRMATION
    assert cleared.pending_action is None
    assert cleared.pending_confirmation is None
    assert cleared.status == ConversationStatus.LISTENING


@pytest.mark.asyncio
async def test_optimistic_version_rejects_stale_writer():
    user = await _user("phase2-version@example.com")
    conversation_id = uuid.uuid4()
    async with async_session() as db:
        initial = await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
        assert initial is not None
        updated = await conversation_state_manager.patch(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            patch=ConversationStatePatch(current_topic="new topic"),
            expected_version=initial.version,
        )
        with pytest.raises(ConversationStateConflictError):
            await conversation_state_manager.patch(
                db,
                user_id=user.id,
                conversation_id=conversation_id,
                patch=ConversationStatePatch(current_topic="stale topic"),
                expected_version=initial.version,
            )

    assert updated.version == initial.version + 1


@pytest.mark.asyncio
async def test_state_rejects_cross_user_conversation_access():
    owner = await _user("phase2-owner@example.com")
    intruder = await _user("phase2-intruder@example.com")
    conversation_id = uuid.uuid4()
    async with async_session() as db:
        await conversation_state_manager.load(
            db,
            user_id=owner.id,
            conversation_id=conversation_id,
        )
    await delete_context_cache(str(intruder.id), conversation_state_manager._cache_id(conversation_id))
    async with async_session() as db:
        with pytest.raises(ValueError, match="authenticated user"):
            await conversation_state_manager.load(
                db,
                user_id=intruder.id,
                conversation_id=conversation_id,
                use_cache=False,
            )


@pytest.mark.asyncio
async def test_interruption_is_durable_and_clears_active_turn():
    user = await _user("phase2-interrupt@example.com")
    conversation_id = uuid.uuid4()
    await update_voice_session_state(
        str(user.id),
        str(conversation_id),
        current_turn_id="turn-7",
        status="ai_speaking",
    )
    interrupted = await mark_interrupted(
        str(user.id),
        str(conversation_id),
        turn_id="turn-7",
    )
    await delete_context_cache(str(user.id), conversation_state_manager._cache_id(conversation_id))
    restored = await get_voice_session_state(str(user.id), str(conversation_id))

    assert interrupted["last_interruption"]["turn_id"] == "turn-7"
    assert restored["status"] == "interrupted"
    assert restored["current_turn_id"] is None
    assert restored["last_interruption"]["turn_id"] == "turn-7"


@pytest.mark.asyncio
async def test_text_turn_creates_and_updates_canonical_state():
    client, headers, _user_id = await _authed_client("phase2-text@example.com")
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
            return_value=_response(),
        ):
            response = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "Let us focus on the Qring launch."},
            )
        assert response.status_code == 200
        conversation_id = uuid.UUID(response.json()["session_id"])
        async with async_session() as db:
            record = await db.get(ConversationStateRecord, conversation_id)
            state = await conversation_state_manager.load(
                db,
                user_id=record.user_id,
                conversation_id=conversation_id,
                use_cache=False,
            )
        assert state is not None
        assert state.current_topic == "Let us focus on the Qring launch."
        assert state.last_ai_response == "I am with you."
        assert state.current_emotion.emotion == "neutral"
        assert state.user_intent == "companion"
        assert "Qring launch" in state.conversation_summary
        assert state.pending_action is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_multi_turn_state_continues_without_duplicate_records():
    client, headers, user_id = await _authed_client("phase2-continuity@example.com")
    conversation_id = str(uuid.uuid4())
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
            side_effect=[_response("First reply."), _response("Second reply.")],
        ):
            first = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "First topic", "session_id": conversation_id},
            )
            second = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "Continue that topic", "session_id": conversation_id},
            )
        assert first.status_code == second.status_code == 200
        async with async_session() as db:
            state = await conversation_state_manager.load(
                db,
                user_id=user_id,
                conversation_id=uuid.UUID(conversation_id),
                use_cache=False,
            )
            records = list(
                (
                    await db.execute(
                        select(ConversationStateRecord).where(
                            ConversationStateRecord.conversation_id == uuid.UUID(conversation_id)
                        )
                    )
                ).scalars()
            )
        assert state is not None
        assert "First topic" in state.conversation_summary
        assert "Continue that topic" in state.conversation_summary
        assert state.last_ai_response == "Second reply."
        assert len(records) == 1
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_deleted_conversation_cannot_be_resurrected_from_state_cache():
    client, headers, user_id = await _authed_client("phase2-delete-state@example.com")
    conversation_id = uuid.uuid4()
    try:
        with patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
            return_value=_response(),
        ):
            created = await client.post(
                "/api/v2/turn/text",
                headers=headers,
                json={"text": "Temporary conversation", "session_id": str(conversation_id)},
            )
        assert created.status_code == 200
        deleted = await client.delete(f"/api/v2/conversations/{conversation_id}", headers=headers)
        assert deleted.status_code == 200

        async with async_session() as db:
            state = await conversation_state_manager.load(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                create=False,
            )
            record = await db.get(ConversationStateRecord, conversation_id)
        assert state is None
        assert record is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_cached_state_load_p95_is_under_phase2_budget():
    user = await _user("phase2-latency@example.com")
    conversation_id = uuid.uuid4()
    async with async_session() as db:
        await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
        samples = []
        for _ in range(50):
            started = time.perf_counter()
            await conversation_state_manager.load(
                db,
                user_id=user.id,
                conversation_id=conversation_id,
            )
            samples.append((time.perf_counter() - started) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 25, f"cached state load p95 {p95:.2f}ms exceeds 25ms"


@pytest.mark.asyncio
async def test_state_mutation_p95_is_under_phase2_budget():
    user = await _user("phase2-write-latency@example.com")
    conversation_id = uuid.uuid4()
    samples = []
    async with async_session() as db:
        await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
        )
        for index in range(20):
            started = time.perf_counter()
            await conversation_state_manager.patch(
                db,
                user_id=user.id,
                conversation_id=conversation_id,
                patch=ConversationStatePatch(current_topic=f"topic-{index}"),
            )
            samples.append((time.perf_counter() - started) * 1000)
    p95 = statistics.quantiles(samples, n=20)[18]
    assert p95 < 75, f"state mutation p95 {p95:.2f}ms exceeds 75ms"


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_process_cache():
    failing_redis = AsyncMock()
    failing_redis.set.side_effect = ConnectionError("redis unavailable")
    failing_redis.get.side_effect = ConnectionError("redis unavailable")
    cache_id = f"phase2-redis-fallback-{uuid.uuid4()}"
    with patch("app.services.context_cache._get_redis", return_value=failing_redis):
        await context_cache.set_context_cache("phase2-user", cache_id, {"value": "durable fallback"})
        restored = await context_cache.get_context_cache("phase2-user", cache_id)
    assert restored == {"value": "durable fallback"}


@pytest.mark.asyncio
async def test_cancelled_orchestration_does_not_leave_stale_active_turn():
    user = await _user("phase2-cancelled-turn@example.com")
    conversation_id = uuid.uuid4()
    request = ConversationInput(
        user_id=user.id,
        conversation_id=conversation_id,
        modality=InputModality.TEXT,
        text="Wait while thinking",
        turn_id="cancelled-phase2-turn",
    )

    class SlowBrain:
        async def stream(self, _request, _context):
            await asyncio.sleep(60)
            if False:
                yield {}

    async with async_session() as db:
        orchestrator = ConversationOrchestrator(
            SlowBrain(),
            state_manager=conversation_state_manager,
        )

        async def consume():
            async for _event in orchestrator.stream(
                request,
                OrchestrationContext(db=db, user=user),
            ):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    async with async_session() as db:
        state = await conversation_state_manager.load(
            db,
            user_id=user.id,
            conversation_id=conversation_id,
            use_cache=False,
        )
    assert state is not None
    assert state.status == ConversationStatus.INTERRUPTED
    assert state.current_turn_id is None
    assert state.last_interruption and state.last_interruption.turn_id == "cancelled-phase2-turn"


def test_live_session_state_survives_real_websocket_reconnect_path():
    user = asyncio.run(_user("phase2-real-ws@example.com"))
    token = create_access_token(user.id, user.email)

    async def fake_tts(_text, voice=None):
        if False:
            yield b"", "audio/mpeg"

    with (
        patch(
            "app.services.companion_orchestrator.generate_companion_response",
            new_callable=AsyncMock,
            return_value=_response("Persistent voice reply."),
        ),
        patch("app.routers.ws_session.synthesize_stream", side_effect=fake_tts),
        patch("app.routers.ws_session._rate_limiter") as limiter,
    ):
        limiter.allow.return_value = True
        with TestClient(app) as client:
            with client.websocket_connect(f"/api/v2/ws/session?token={token}") as websocket:
                started = json.loads(websocket.receive_text())
                session_id = uuid.UUID(started["session_id"])
                websocket.send_text(
                    json.dumps(
                        {
                            "type": "text_turn",
                            "turn_id": "phase2-ws-turn",
                            "text": "Remember this thread across reconnects.",
                        }
                    )
                )
                for _ in range(30):
                    message = json.loads(websocket.receive_text())
                    if message.get("type") == "turn_complete":
                        assert message["reply"] == "Persistent voice reply."
                        break
                else:
                    pytest.fail("Live turn did not complete")
                websocket.send_text(json.dumps({"type": "end"}))
                for _ in range(10):
                    if json.loads(websocket.receive_text()).get("type") == "session_ended":
                        break
                else:
                    pytest.fail("Live session did not end cleanly")

    asyncio.run(delete_context_cache(str(user.id), conversation_state_manager._cache_id(session_id)))

    async def load_state():
        async with async_session() as db:
            return await conversation_state_manager.load(
                db,
                user_id=user.id,
                conversation_id=session_id,
                use_cache=False,
            )

    restored = asyncio.run(load_state())
    assert restored is not None
    assert restored.status == ConversationStatus.ENDED
    assert restored.last_ai_response == "Persistent voice reply."
    assert "across reconnects" in restored.conversation_summary
