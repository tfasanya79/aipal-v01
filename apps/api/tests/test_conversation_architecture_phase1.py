from __future__ import annotations

import asyncio
import ast
import statistics
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.conversation.contracts import (
    ConversationInput,
    InputModality,
    OrchestrationContext,
)
from app.conversation.orchestrator import (
    ConversationCancelledError,
    ConversationOrchestrator,
)
from app.services.tool_router import detect_companion_tool


class FakeBrain:
    def __init__(self) -> None:
        self.requests: list[ConversationInput] = []

    async def stream(self, request, _context):
        self.requests.append(request)
        yield {"type": "context_ready", "mode": "companion"}
        yield {"type": "reply_delta", "text": "Unified reply."}
        yield {"type": "sentence_ready", "text": "Unified reply."}
        yield {
            "type": "turn_complete",
            "reply": "Unified reply.",
            "conversation_id": str(request.conversation_id) if request.conversation_id else None,
        }


def _request(modality: InputModality, user_id: uuid.UUID) -> ConversationInput:
    return ConversationInput(user_id=user_id, modality=modality, text="  hello  ")


def _context(user_id: uuid.UUID, *, cancel_event=None) -> OrchestrationContext:
    return OrchestrationContext(
        db=AsyncMock(),
        user=SimpleNamespace(id=user_id),
        cancel_event=cancel_event,
    )


def test_conversation_input_is_normalized_versioned_and_strict():
    user_id = uuid.uuid4()
    request = _request(InputModality.TEXT, user_id)
    assert request.text == "hello"
    assert request.schema_version == "1.0"
    with pytest.raises(ValidationError):
        ConversationInput(
            user_id=user_id,
            modality=InputModality.TEXT,
            text="hello",
            unexpected=True,
        )


@pytest.mark.asyncio
async def test_every_modality_uses_identical_orchestration_and_event_contract():
    user_id = uuid.uuid4()
    brain = FakeBrain()
    orchestrator = ConversationOrchestrator(brain)
    event_shapes = []

    for modality in InputModality:
        events = [
            event
            async for event in orchestrator.stream(
                _request(modality, user_id),
                _context(user_id),
            )
        ]
        event_shapes.append([event.event_type for event in events])
        assert [event.sequence for event in events] == list(range(len(events)))
        assert len({event.event_id for event in events}) == len(events)
        assert all(event.correlation_id == events[0].input_id for event in events)

    assert event_shapes[0] == event_shapes[1] == event_shapes[2]
    assert [request.modality for request in brain.requests] == list(InputModality)


@pytest.mark.asyncio
async def test_request_response_collection_uses_the_same_stream_path():
    user_id = uuid.uuid4()
    brain = FakeBrain()
    result = await ConversationOrchestrator(brain).run(
        _request(InputModality.TEXT, user_id),
        _context(user_id),
    )
    assert result.reply == "Unified reply."
    assert len(brain.requests) == 1


@pytest.mark.asyncio
async def test_terminal_event_adopts_brain_assigned_conversation_id():
    user_id = uuid.uuid4()
    assigned_id = uuid.uuid4()

    class AssigningBrain(FakeBrain):
        async def stream(self, request, _context):
            yield {"type": "turn_complete", "reply": "done", "conversation_id": str(assigned_id)}

    request = _request(InputModality.TEXT, user_id)
    events = [
        event
        async for event in ConversationOrchestrator(AssigningBrain()).stream(
            request,
            _context(user_id),
        )
    ]
    assert events[-1].event_type == "turn_complete"
    assert events[-1].conversation_id == assigned_id


@pytest.mark.asyncio
async def test_cancellation_is_checked_before_brain_execution():
    user_id = uuid.uuid4()
    cancelled = asyncio.Event()
    cancelled.set()
    stream = ConversationOrchestrator(FakeBrain()).stream(
        _request(InputModality.LIVE_VOICE, user_id),
        _context(user_id, cancel_event=cancelled),
    )
    with pytest.raises(ConversationCancelledError):
        await anext(stream)


@pytest.mark.asyncio
async def test_authenticated_user_must_match_contract_user():
    request = _request(InputModality.TEXT, uuid.uuid4())
    stream = ConversationOrchestrator(FakeBrain()).stream(request, _context(uuid.uuid4()))
    with pytest.raises(ValueError, match="authenticated user"):
        await anext(stream)


@pytest.mark.asyncio
async def test_orchestration_overhead_p95_is_below_phase1_budget():
    user_id = uuid.uuid4()
    orchestrator = ConversationOrchestrator(FakeBrain())
    samples_ms = []
    for _ in range(50):
        started = time.perf_counter()
        await orchestrator.run(_request(InputModality.TEXT, user_id), _context(user_id))
        samples_ms.append((time.perf_counter() - started) * 1000)
    p95 = statistics.quantiles(samples_ms, n=20)[18]
    assert p95 < 75, f"orchestration p95 {p95:.2f}ms exceeds 75ms budget"


def test_free_form_language_cannot_keyword_route_tools():
    assert detect_companion_tool("Create a task and check my calendar", None) is None
    assert detect_companion_tool("anything", {"tool": "calendar_service"}) == "calendar_service"


def test_transport_modules_do_not_import_brain_subsystems_directly():
    app_root = Path(__file__).parents[1] / "app"
    forbidden = {
        "app.services.companion_orchestrator",
        "app.services.companion_response_service",
        "app.services.conversation_manager",
        "app.services.memory_service",
        "app.services.tool_router",
    }
    for relative in ("routers/turn.py", "routers/companion.py", "routers/ws_session.py"):
        tree = ast.parse((app_root / relative).read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        )
        assert not imports.intersection(forbidden), f"{relative} bypasses unified orchestration"


def test_all_transport_adapters_reference_the_canonical_service():
    app_root = Path(__file__).parents[1] / "app"
    assert "conversation.service import run_conversation" in (app_root / "routers/turn.py").read_text()
    assert "conversation.service import run_conversation" in (app_root / "routers/companion.py").read_text()
    assert "conversation.service import stream_conversation" in (app_root / "services/voice_turn.py").read_text()
