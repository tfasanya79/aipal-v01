from __future__ import annotations

import json
import statistics
import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.conversation.reasoning import ReasoningDecision, ReasoningToolCall
from app.main import app
from app.services.ai_reasoning_engine import ReasoningContractError, _parse_decision
from app.services.reasoning_policy import validate_reasoning_decision


def _stream_llm(*responses: str):
    calls: list[list[dict[str, str]]] = []
    remaining = iter(responses)

    async def stream(messages, **_kwargs):
        calls.append(messages)
        yield next(remaining)

    stream.calls = calls
    return stream


def _decision(
    *,
    intents: list[dict] | None = None,
    primary_intent: str = "general_conversation",
    mode: str = "companion",
    tool_calls: list[dict] | None = None,
    missing_information: list[str] | None = None,
    pending_action_resolution: str = "none",
    confirmation_message: str | None = None,
) -> dict:
    return {
        "schema_version": "1.0",
        "intents": intents or [{"name": primary_intent, "confidence": 0.94}],
        "primary_intent": primary_intent,
        "missing_information": missing_information or [],
        "mode": mode,
        "emotion": {"emotion": "neutral", "intensity": 1, "urgency": 0},
        "conversation_strategy": "Answer directly and remain grounded.",
        "response_strategy": "Give a concise, natural response.",
        "planning_notes": [],
        "tool_calls": tool_calls or [],
        "confirmation_message": confirmation_message,
        "pending_action_resolution": pending_action_resolution,
    }


async def _authed_client(email: str):
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    registration = await client.post("/api/v2/auth/register", json={"email": email})
    verification = await client.post(
        "/api/v2/auth/verify",
        json={"token": registration.json()["dev_token"]},
    )
    headers = {"Authorization": f"Bearer {verification.json()['access_token']}"}
    return client, headers


def test_reasoning_contract_accepts_multiple_intents_and_ordered_tools():
    decision = ReasoningDecision.model_validate(
        _decision(
            intents=[
                {"name": "review_today", "confidence": 0.96},
                {"name": "review_tasks", "confidence": 0.88},
            ],
            primary_intent="review_today",
            mode="assistant",
            tool_calls=[
                {
                    "call_id": "calendar",
                    "name": "calendar_service",
                    "arguments": {},
                    "depends_on": [],
                    "rationale": "Load today's agenda.",
                    "requires_confirmation": False,
                },
                {
                    "call_id": "tasks",
                    "name": "task_service",
                    "arguments": {},
                    "depends_on": ["calendar"],
                    "rationale": "Add open tasks after the agenda.",
                    "requires_confirmation": False,
                },
            ],
        )
    )

    assert len(decision.intents) == 2
    assert [call.call_id for call in decision.tool_calls] == ["calendar", "tasks"]


def test_reasoning_contract_rejects_markdown_unknown_fields_and_forward_dependencies():
    with pytest.raises(ReasoningContractError, match="strict JSON"):
        _parse_decision("Here is the answer: {}")

    payload = _decision()
    payload["chain_of_thought"] = "hidden reasoning must not be accepted"
    with pytest.raises(ReasoningContractError, match="schema validation"):
        _parse_decision(json.dumps(payload))

    payload = _decision(
        tool_calls=[
            {
                "call_id": "second",
                "name": "task_service",
                "arguments": {},
                "depends_on": ["first"],
                "rationale": "Invalid forward dependency.",
                "requires_confirmation": False,
            }
        ]
    )
    with pytest.raises(ValueError, match="earlier call"):
        ReasoningDecision.model_validate(payload)


def test_backend_policy_rejects_unknown_tools_and_arguments():
    decision = ReasoningDecision.model_validate(
        _decision(
            tool_calls=[
                {
                    "call_id": "bad_tool",
                    "name": "delete_everything",
                    "arguments": {},
                    "depends_on": [],
                    "rationale": "Must be rejected.",
                    "requires_confirmation": False,
                },
                {
                    "call_id": "bad_args",
                    "name": "task_service",
                    "arguments": {"user_id": "someone-else"},
                    "depends_on": [],
                    "rationale": "Cross-user argument must be rejected.",
                    "requires_confirmation": False,
                },
            ]
        )
    )

    validation = validate_reasoning_decision(decision, conversation_state=None)

    assert not validation.executable_calls
    assert "Unknown tool" in validation.errors[0]
    assert "Unexpected arguments" in validation.errors[1]


def test_backend_policy_requires_and_validates_durable_confirmation():
    call = ReasoningToolCall(
        call_id="create_room",
        name="project_rooms",
        arguments={"room_name": "Qring Pilot"},
        rationale="Create the requested project room.",
    )
    first = ReasoningDecision.model_validate(_decision(tool_calls=[call.model_dump()]))
    validation = validate_reasoning_decision(first, conversation_state=None)
    assert validation.pending_call == call
    assert not validation.executable_calls

    state = {
        "pending_action": {
            "fields": {"tool_call": call.model_dump(mode="json")},
        }
    }
    confirmed = ReasoningDecision.model_validate(
        _decision(pending_action_resolution="confirm")
    )
    validation = validate_reasoning_decision(confirmed, conversation_state=state)
    assert validation.executable_calls == [call]
    assert validation.pending_call is None

    forged_apply = ReasoningDecision.model_validate(
        _decision(
            tool_calls=[
                {
                    "call_id": "forged_apply",
                    "name": "planner_engine",
                    "arguments": {"action": "confirm_draft"},
                    "depends_on": [],
                    "rationale": "Must not bypass durable confirmation.",
                    "requires_confirmation": False,
                }
            ]
        )
    )
    validation = validate_reasoning_decision(forged_apply, conversation_state=None)
    assert not validation.executable_calls
    assert "durable confirmation" in validation.errors[0]


def test_reasoning_validation_latency_budget():
    decision = ReasoningDecision.model_validate(
        _decision(
            tool_calls=[
                {
                    "call_id": f"call_{index}",
                    "name": "task_service",
                    "arguments": {},
                    "depends_on": [f"call_{index - 1}"] if index else [],
                    "rationale": "Read bounded task context.",
                    "requires_confirmation": False,
                }
                for index in range(4)
            ]
        )
    )
    samples: list[float] = []
    for _ in range(500):
        started = time.perf_counter()
        validate_reasoning_decision(decision, conversation_state=None)
        samples.append((time.perf_counter() - started) * 1_000)
    assert statistics.quantiles(samples, n=20)[18] < 10


@pytest.mark.asyncio
async def test_rest_turn_uses_reasoning_then_final_response_with_tool_evidence():
    client, headers = await _authed_client("phase7-tool-loop@example.com")
    reasoning = _decision(
        intents=[
            {"name": "review_tasks", "confidence": 0.97},
            {"name": "prioritize_day", "confidence": 0.82},
        ],
        primary_intent="review_tasks",
        mode="assistant",
        tool_calls=[
            {
                "call_id": "tasks",
                "name": "task_service",
                "arguments": {},
                "depends_on": [],
                "rationale": "Load open tasks.",
                "requires_confirmation": False,
            }
        ],
    )
    try:
        stream = _stream_llm(
            "You have a clear task list. Start with the highest priority item."
        )
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=[json.dumps(reasoning)],
            ) as llm,
            patch("app.services.reasoned_turn_service.llm_chat_stream", new=stream),
        ):
            settings.return_value.ai_reasoning_enabled = True
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Show my tasks and help me prioritize."},
            )

        assert response.status_code == 200
        assert response.json()["reply"].startswith("You have a clear task list")
        assert llm.await_count == 1
        assert llm.await_args_list[0].kwargs["max_tokens"] == 384
        assert llm.await_args_list[0].kwargs["response_schema"]
        reasoning_messages = llm.await_args_list[0].args[0]
        final_messages = stream.calls[0]
        assert "Response purpose: reasoning" in reasoning_messages[0]["content"]
        assert "strict JSON only" in reasoning_messages[0]["content"]
        assert "Response purpose: final_response" in final_messages[0]["content"]
        assert '"tool": "task_service"' in final_messages[1]["content"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_mutating_tool_requires_durable_confirmation_before_execution():
    client, headers = await _authed_client("phase7-confirmation@example.com")
    initial = _decision(
        primary_intent="create_project_room",
        mode="assistant",
        tool_calls=[
            {
                "call_id": "create_qring_room",
                "name": "project_rooms",
                "arguments": {"room_name": "Qring Pilot"},
                "depends_on": [],
                "rationale": "Create the room the user requested.",
                "requires_confirmation": False,
            }
        ],
        confirmation_message="Should I create the Qring Pilot project room?",
    )
    confirmed = _decision(
        primary_intent="confirm_pending_action",
        mode="assistant",
        pending_action_resolution="confirm",
    )
    try:
        stream = _stream_llm(
            "Should I create the Qring Pilot project room?",
            "The Qring Pilot project room is ready.",
        )
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=[
                    json.dumps(initial),
                    json.dumps(confirmed),
                ],
            ),
            patch("app.services.reasoned_turn_service.llm_chat_stream", new=stream),
        ):
            settings.return_value.ai_reasoning_enabled = True
            first = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Create a project room for Qring Pilot."},
            )
            assert first.status_code == 200
            assert first.json()["requires_confirmation"] is True
            conversation_id = first.json()["conversation_id"]

            second = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Yes, create it.", "conversation_id": conversation_id},
            )

        assert second.status_code == 200
        assert second.json()["requires_confirmation"] is False
        assert second.json()["reply"] == "The Qring Pilot project room is ready."
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_planner_draft_is_generated_then_applied_only_after_confirmation():
    client, headers = await _authed_client("phase7-planner-confirmation@example.com")
    draft = _decision(
        primary_intent="plan_day",
        mode="planner",
        tool_calls=[
            {
                "call_id": "draft_day",
                "name": "planner_engine",
                "arguments": {"plan_kind": "daily"},
                "depends_on": [],
                "rationale": "Draft a day plan from the user's constraints.",
                "requires_confirmation": True,
            }
        ],
        confirmation_message="I drafted the plan. Should I add it to Today?",
    )
    confirm = _decision(
        primary_intent="confirm_pending_action",
        mode="planner",
        pending_action_resolution="confirm",
    )
    try:
        stream = _stream_llm(
            "I drafted the plan. Should I add it to Today?",
            "Your plan is now on Today.",
        )
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=[
                    json.dumps(draft),
                    json.dumps(confirm),
                ],
            ),
            patch("app.services.reasoned_turn_service.llm_chat_stream", new=stream),
        ):
            settings.return_value.ai_reasoning_enabled = True
            first = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Plan tomorrow with coding at 9am and a swim at 5pm."},
            )
            assert first.status_code == 200
            assert first.json()["requires_confirmation"] is True
            assert first.json()["plan_draft"]["proposed_tasks"]

            second = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={
                    "message": "Yes, add that plan.",
                    "conversation_id": first.json()["conversation_id"],
                },
            )

        assert second.status_code == 200
        assert second.json()["requires_confirmation"] is False
        assert second.json()["reply"] == "Your plan is now on Today."
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_invalid_reasoning_contract_falls_back_to_compatibility_path():
    client, headers = await _authed_client("phase7-invalid-contract@example.com")
    try:
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=["not-json", "Compatibility reply."],
            ) as llm,
        ):
            settings.return_value.ai_reasoning_enabled = True
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "Tell me something useful."},
            )

        assert response.status_code == 200
        assert response.json()["reply"] == "Compatibility reply."
        assert llm.await_count == 2
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_live_voice_uses_the_same_reasoning_engine_with_voice_output_contract():
    client, headers = await _authed_client("phase7-live-voice@example.com")
    reasoning = _decision(primary_intent="voice_conversation")
    try:
        stream = _stream_llm("I’m listening. Keep going.")
        with (
            patch("app.services.companion_orchestrator.get_settings") as settings,
            patch(
                "app.services.companion_response_service.llm_chat",
                new_callable=AsyncMock,
                side_effect=[json.dumps(reasoning)],
            ) as llm,
            patch("app.services.reasoned_turn_service.llm_chat_stream", new=stream),
        ):
            settings.return_value.ai_reasoning_enabled = True
            response = await client.post(
                "/api/v2/companion/turn",
                headers=headers,
                json={"message": "I need to think this through.", "source": "voice"},
            )

        assert response.status_code == 200
        assert response.json()["reply"] == "I’m listening. Keep going."
        assert "Output channel: voice" in llm.await_args_list[0].args[0][0]["content"]
        assert "Response purpose: reasoning" in llm.await_args_list[0].args[0][0]["content"]
        assert "Response purpose: final_response" in stream.calls[0][0]["content"]
    finally:
        await client.aclose()
