from __future__ import annotations

import ast
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.db import async_session
from app.conversation.contracts import InputModality
from app.conversation.service import stream_conversation
from app.main import app
from app.models import ConversationStateRecord, Message, User
from app.services.tool_registry import tool_registry


TESTS = Path(__file__).resolve().parent


QUALITY_EVIDENCE = {
    "unit": (
        "test_prompt_engine_phase6.py",
        "test_canonical_prompt_contains_every_phase6_contract_section",
    ),
    "integration": (
        "test_ai_reasoning_phase7.py",
        "test_rest_turn_uses_reasoning_then_final_response_with_tool_evidence",
    ),
    "load": (
        "test_tool_registry_phase8.py",
        "test_registry_concurrent_execution_keeps_contexts_isolated",
    ),
    "voice_interruption": (
        "test_streaming_response_phase9.py",
        "test_cancellation_closes_stream_quickly_and_does_not_persist_partial_reply",
    ),
    "memory": (
        "test_memory_manager_phase5.py",
        "test_query_retrieval_uses_bounded_vector_candidates_across_domains",
    ),
    "planner": (
        "test_ai_reasoning_phase7.py",
        "test_planner_draft_is_generated_then_applied_only_after_confirmation",
    ),
    "calendar": (
        "test_quality_phase10.py",
        "test_text_to_voice_multi_turn_keeps_history_state_and_registry_path",
    ),
    "tool_execution": (
        "test_tool_registry_phase8.py",
        "test_text_voice_and_explicit_ui_use_the_same_registry_executor",
    ),
    "multi_turn": (
        "test_quality_phase10.py",
        "test_text_to_voice_multi_turn_keeps_history_state_and_registry_path",
    ),
    "continuity": (
        "test_conversation_state_phase2.py",
        "test_multi_turn_state_continues_without_duplicate_records",
    ),
    "security": (
        "test_ai_reasoning_phase7.py",
        "test_backend_policy_rejects_unknown_tools_and_arguments",
    ),
    "database": (
        "test_memory_manager_phase5_postgres.py",
        "test_phase5_pgvector_hnsw_backfill_retrieval_and_latency",
    ),
}


def _decision(*, tool: str, call_id: str, depends_on: list[str] | None = None) -> dict:
    return {
        "schema_version": "1.0",
        "intents": [{"name": f"use_{tool}", "confidence": 0.98}],
        "primary_intent": f"use_{tool}",
        "missing_information": [],
        "mode": "assistant",
        "emotion": {"emotion": "neutral", "intensity": 1, "urgency": 0},
        "conversation_strategy": "Continue from durable context.",
        "response_strategy": "Answer only from validated tool evidence.",
        "planning_notes": [],
        "tool_calls": [
            {
                "call_id": call_id,
                "name": tool,
                "arguments": {},
                "depends_on": depends_on or [],
                "rationale": "Read authenticated context.",
                "requires_confirmation": False,
            }
        ],
        "confirmation_message": None,
        "pending_action_resolution": "none",
    }


async def _client(email: str) -> tuple[AsyncClient, dict[str, str]]:
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    registration = await client.post("/api/v2/auth/register", json={"email": email})
    verification = await client.post(
        "/api/v2/auth/verify",
        json={"token": registration.json()["dev_token"]},
    )
    return client, {
        "Authorization": f"Bearer {verification.json()['access_token']}"
    }


def test_required_quality_evidence_is_present_and_auditable():
    assert set(QUALITY_EVIDENCE) == {
        "unit",
        "integration",
        "load",
        "voice_interruption",
        "memory",
        "planner",
        "calendar",
        "tool_execution",
        "multi_turn",
        "continuity",
        "security",
        "database",
    }
    for category, (filename, function_name) in QUALITY_EVIDENCE.items():
        path = TESTS / filename
        assert path.is_file(), f"{category} gate references missing file {filename}"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert function_name in functions, (
            f"{category} gate references missing test {filename}::{function_name}"
        )


@pytest.mark.asyncio
async def test_text_to_voice_multi_turn_keeps_history_state_and_registry_path():
    email = "phase10-continuity@example.com"
    client, headers = await _client(email)
    final_responses = iter(
        (
            "Your calendar is clear, so we can keep Project Atlas in focus.",
            "Keep Project Atlas first; your task list is the next constraint.",
        )
    )

    async def final_stream(_messages, **_kwargs):
        yield next(final_responses)

    decisions = [
        json.dumps(_decision(tool="calendar_service", call_id="calendar")),
        json.dumps(_decision(tool="task_service", call_id="tasks")),
    ]
    original_execute = tool_registry.execute
    try:
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=decisions,
            ) as reasoning_llm,
            patch(
                "app.services.reasoned_turn_service.llm_chat_stream",
                new=final_stream,
            ),
            patch.object(
                tool_registry,
                "execute",
                new_callable=AsyncMock,
                wraps=original_execute,
            ) as execute,
        ):
            settings.return_value.ai_reasoning_enabled = True
            settings.return_value.ai_streaming_enabled = True
            first = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={
                    "message": "Check my calendar while I think about Project Atlas.",
                    "source": "text",
                },
            )
            assert first.status_code == 200
            conversation_id = first.json()["conversation_id"]

            second = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={
                    "message": "What should I do first?",
                    "source": "voice",
                    "conversation_id": conversation_id,
                },
            )

        assert second.status_code == 200
        assert "Project Atlas" in second.json()["reply"]
        assert execute.await_count == 2
        assert [call.args[1] for call in execute.await_args_list] == [
            "calendar_service",
            "task_service",
        ]
        assert [call.args[0].source for call in execute.await_args_list] == [
            "text",
            "voice",
        ]

        second_reasoning_prompt = "\n".join(
            message["content"]
            for message in reasoning_llm.await_args_list[1].args[0]
        )
        assert "Check my calendar while I think about Project Atlas." in second_reasoning_prompt
        assert "Your calendar is clear" in second_reasoning_prompt

        async with async_session() as db:
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one()
            state_count = (
                await db.execute(
                    select(func.count())
                    .select_from(ConversationStateRecord)
                    .where(
                        ConversationStateRecord.user_id == user.id,
                        ConversationStateRecord.conversation_id
                        == uuid.UUID(conversation_id),
                    )
                )
            ).scalar_one()
            messages = list(
                (
                    await db.execute(
                        select(Message)
                        .where(Message.conversation_id == uuid.UUID(conversation_id))
                        .order_by(Message.created_at)
                    )
                ).scalars()
            )
        assert state_count == 1
        assert [message.source for message in messages] == [
            "text",
            "text",
            "voice",
            "voice",
        ]
        assert [message.role for message in messages] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_failed_tool_stops_dependents_and_remains_grounded_in_terminal_event():
    email = "phase10-tool-failure@example.com"
    client, _headers = await _client(email)
    reasoning = _decision(tool="task_service", call_id="tasks")
    reasoning["tool_calls"].append(
        {
            "call_id": "calendar",
            "name": "calendar_service",
            "arguments": {},
            "depends_on": ["tasks"],
            "rationale": "This must stop after the failed dependency.",
            "requires_confirmation": False,
        }
    )

    async def final_stream(_messages, **_kwargs):
        yield "I could not load the task evidence, so I did not continue."

    try:
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                return_value=json.dumps(reasoning),
            ),
            patch(
                "app.services.reasoned_turn_service.llm_chat_stream",
                new=final_stream,
            ),
            patch.object(
                tool_registry,
                "execute",
                new_callable=AsyncMock,
                side_effect=RuntimeError("dependency unavailable"),
            ) as execute,
        ):
            settings.return_value.ai_reasoning_enabled = True
            settings.return_value.ai_streaming_enabled = True
            async with async_session() as db:
                user = (
                    await db.execute(select(User).where(User.email == email))
                ).scalar_one()
                events = [
                    event
                    async for event in stream_conversation(
                        db,
                        user,
                        "Check tasks, then my calendar.",
                        modality=InputModality.TEXT,
                    )
                ]

        terminal = next(
            event for event in events if event.event_type == "turn_complete"
        )
        body = terminal.payload
        assert execute.await_count == 1
        assert body["tool_actions"] == [
            {"type": "task_service", "call_id": "tasks", "status": "failed", "duration_ms": 0}
        ]
        assert body["reasoning_validation_errors"] == [
            "task_service failed: RuntimeError"
        ]
        assert body["reply"] == (
            "I could not load the task evidence, so I did not continue."
        )
    finally:
        await client.aclose()
