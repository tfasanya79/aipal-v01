from __future__ import annotations

import asyncio
import ast
import json
import statistics
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.ai_reasoning_engine import reason_about_turn
from app.services.tool_router import execute_companion_tool
from app.services.tool_registry import (
    EmptyArguments,
    ToolArgumentError,
    ToolDefinition,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolRegistry,
    UnknownToolError,
    tool_registry,
)


APP_SERVICES = Path(__file__).resolve().parents[1] / "app" / "services"


def _decision(*, source_tool: str = "task_service") -> dict:
    return {
        "schema_version": "1.0",
        "intents": [{"name": "review_tasks", "confidence": 0.97}],
        "primary_intent": "review_tasks",
        "missing_information": [],
        "mode": "assistant",
        "emotion": {"emotion": "neutral", "intensity": 1, "urgency": 0},
        "conversation_strategy": "Load grounded context.",
        "response_strategy": "Respond concisely.",
        "planning_notes": [],
        "tool_calls": [
            {
                "call_id": f"load_{source_tool}",
                "name": source_tool,
                "arguments": {},
                "depends_on": [],
                "rationale": "Load the requested data.",
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
    return client, {"Authorization": f"Bearer {verification.json()['access_token']}"}


def test_registry_is_the_complete_immutable_capability_catalog():
    assert tool_registry.names == (
        "planner_engine",
        "meeting_assistant",
        "project_rooms",
        "life_map",
        "morning_brief",
        "memory_service",
        "calendar_service",
        "task_service",
    )
    assert tool_registry.resolve("plan_my_day") == "planner_engine"
    assert tool_registry.resolve("project_room") == "project_rooms"
    assert len(tool_registry.instructions) == len(tool_registry.names)
    assert all(name in instruction for name, instruction in zip(tool_registry.names, tool_registry.instructions))


def test_registry_fails_fast_for_duplicate_names_and_aliases():
    async def handler(_context, _arguments):
        return ToolExecutionResult(tool_action="noop", reply="ok")

    definition = ToolDefinition(
        name="one",
        aliases=("shared",),
        description="One.",
        arguments_model=EmptyArguments,
        handler=handler,
    )
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry((definition, definition))
    other = ToolDefinition(
        name="two",
        aliases=("shared",),
        description="Two.",
        arguments_model=EmptyArguments,
        handler=handler,
    )
    with pytest.raises(ValueError, match="Duplicate tool alias"):
        ToolRegistry((definition, other))


def test_registry_rejects_unknown_extra_cross_user_and_malformed_arguments():
    with pytest.raises(UnknownToolError):
        tool_registry.validate_arguments("not_registered", {})
    with pytest.raises(ToolArgumentError, match="user_id"):
        tool_registry.validate_arguments("task_service", {"user_id": "another-user"})
    with pytest.raises(ToolArgumentError, match="meeting_id"):
        tool_registry.validate_arguments("meeting_assistant", {"meeting_id": "not-a-uuid"})
    with pytest.raises(ToolArgumentError, match="date"):
        tool_registry.validate_arguments("planner_engine", {"date": "not-a-date"})


def test_backend_confirmation_policy_cannot_be_weakened_by_model_output():
    assert tool_registry.requires_confirmation(
        "project_rooms", {"room_name": "Qring Pilot"}
    )
    assert tool_registry.requires_confirmation(
        "planner_engine", {"action": "confirm_draft"}
    )
    assert not tool_registry.requires_confirmation(
        "project_rooms", {"room_id": "00000000-0000-0000-0000-000000000001"}
    )
    assert not tool_registry.requires_confirmation("task_service", {})


@pytest.mark.asyncio
async def test_prompt_catalog_is_generated_from_registry_metadata():
    captured: list[dict[str, str]] = []

    async def fake_llm(messages, **_kwargs):
        captured.extend(messages)
        return json.dumps(_decision())

    await reason_about_turn(
        user_message="Show my tasks.",
        output_channel="text",
        context_items=[],
        conversation_history=[],
        user_preferences={},
        conversation_state=None,
        llm=fake_llm,
    )

    system = captured[0]["content"]
    for name in tool_registry.names:
        assert name in system
    for instruction in tool_registry.instructions:
        assert instruction in system


@pytest.mark.asyncio
async def test_text_voice_and_explicit_ui_use_the_same_registry_executor():
    client, headers = await _client("phase8-one-executor@example.com")
    try:
        llm_responses = [
            json.dumps(_decision()),
            json.dumps(_decision()),
        ]
        streamed_responses = iter(
            ["Here are your open tasks.", "Here are your open tasks by voice."]
        )

        async def final_stream(_messages, **_kwargs):
            yield next(streamed_responses)

        original_execute = tool_registry.execute
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=llm_responses,
            ),
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
            patch(
                "app.services.tool_router.generate_policy_text",
                new_callable=AsyncMock,
                return_value="Here are your open tasks from the explicit tool.",
            ),
        ):
            settings.return_value.ai_reasoning_enabled = True
            text_response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Show my tasks.", "source": "text"},
            )
            voice_response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Show my tasks.", "source": "voice"},
            )
            explicit_response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={
                    "message": "Open tasks",
                    "source": "text",
                    "source_context": {"tool": "task_service"},
                },
            )

        assert text_response.status_code == 200
        assert voice_response.status_code == 200
        assert explicit_response.status_code == 200
        assert execute.await_count == 3
        contexts = [item.args[0] for item in execute.await_args_list]
        assert all(isinstance(context, ToolExecutionContext) for context in contexts)
        assert [context.source for context in contexts] == ["text", "voice", "text"]
        assert [item.args[1] for item in execute.await_args_list] == ["task_service"] * 3
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_explicit_mutation_stops_before_handler_and_returns_durable_pending_call():
    with patch.object(tool_registry, "execute", new_callable=AsyncMock) as execute:
        payload = await execute_companion_tool(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            "Create Qring Pilot",
            source_context={"tool": "project_rooms", "room_name": "Qring Pilot"},
        )
    assert payload is not None
    assert payload["requires_confirmation"] is True
    assert payload["pending_action"]["fields"]["tool_call"]["name"] == "project_rooms"
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_invalid_arguments_fail_closed_before_handler():
    with patch.object(tool_registry, "execute", new_callable=AsyncMock) as execute:
        payload = await execute_companion_tool(
            None,  # type: ignore[arg-type]
            None,  # type: ignore[arg-type]
            "Open this meeting",
            source_context={"tool": "meeting_assistant", "meeting_id": "not-a-uuid"},
        )
    assert payload is not None
    assert payload["tool_action"] == "validation_failed"
    execute.assert_not_awaited()


def test_registry_validation_and_lookup_latency_budget():
    samples: list[float] = []
    for _ in range(1_000):
        started = time.perf_counter()
        assert tool_registry.resolve("daily_plan") == "planner_engine"
        tool_registry.validate_arguments(
            "planner_engine", {"plan_kind": "daily", "date": "2026-07-17"}
        )
        samples.append((time.perf_counter() - started) * 1_000)
    assert statistics.quantiles(samples, n=20)[18] < 10


@pytest.mark.asyncio
async def test_registry_concurrent_execution_keeps_contexts_isolated():
    async def handler(context, _arguments):
        await asyncio.sleep(0)
        return ToolExecutionResult(
            tool_action="echo",
            tool_result={"user": context.user, "message": context.message},
            reply="ok",
        )

    registry = ToolRegistry(
        (
            ToolDefinition(
                name="echo",
                description="Echo isolated context.",
                arguments_model=EmptyArguments,
                handler=handler,
            ),
        )
    )
    results = await asyncio.gather(
        *(
            registry.execute(
                ToolExecutionContext(
                    db=None,  # type: ignore[arg-type]
                    user=f"user-{index}",  # type: ignore[arg-type]
                    message=f"message-{index}",
                    call_id=f"call-{index}",
                ),
                "echo",
                {},
            )
            for index in range(250)
        )
    )
    assert [result.tool_result for result in results] == [
        {"user": f"user-{index}", "message": f"message-{index}"}
        for index in range(250)
    ]


def test_no_conversational_tool_switch_or_private_planner_execution_bypass():
    router_source = (APP_SERVICES / "tool_router.py").read_text(encoding="utf-8")
    reasoned_source = (APP_SERVICES / "reasoned_turn_service.py").read_text(encoding="utf-8")
    prompt_source = (APP_SERVICES / "prompt_builder.py").read_text(encoding="utf-8")
    policy_source = (APP_SERVICES / "reasoning_policy.py").read_text(encoding="utf-8")

    router_tree = ast.parse(router_source)
    comparisons = [
        node for node in ast.walk(router_tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "tool"
        and any(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in node.comparators)
    ]
    assert comparisons == []
    assert "confirm_draft(" not in reasoned_source
    assert "AVAILABLE_CONVERSATION_TOOLS" not in prompt_source
    assert "TOOL_ARGUMENTS" not in policy_source
