from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.services.companion_response_service import (
    _clean_user_facing_reply,
    generate_companion_response,
)


async def _call_service(message: str, *, memories: list[dict] | None = None, tasks: list[dict] | None = None):
    with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "I hear you. Let's slow it down and think through what matters."
        result = await generate_companion_response(
            user_message=message,
            conversation_history=[{"role": "user", "content": "I have been working on Qring."}],
            tasks=tasks or [],
            memories=memories or [],
            goals=[{"title": "Grow Qring", "importance": 7, "confidence": 0.9}],
            commitments=[{"title": "Call estate chairmen", "confidence": 0.9}],
            projects=[{"name": "Qring", "confidence": 0.9}],
            people=[{"name": "Stephen", "entity_type": "person", "confidence": 0.8}],
            emotional_patterns=[{"summary": "Stress rises before sales calls.", "confidence": 0.8}],
            user_preferences={"tone": "warm", "response_length": "balanced"},
        )
        return result, mock_llm.call_args.args[0]


async def _call_service_with_reply(message: str, reply: str, *, memories: list[dict] | None = None):
    with patch("app.services.companion_response_service.llm_chat", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = reply
        result = await generate_companion_response(
            user_message=message,
            conversation_history=[],
            tasks=[],
            memories=memories or [],
            goals=[],
            commitments=[],
            projects=[],
            people=[],
            emotional_patterns=[],
            user_preferences={},
        )
        return result, mock_llm.call_args.args[0]


@pytest.mark.asyncio
async def test_generate_companion_response_uses_canonical_prompt():
    _result, messages = await _call_service("I'm stressed about sales.")

    assert messages[0]["role"] == "system"
    assert "You are AiPal." in messages[0]["content"]
    assert "Understanding comes before planning." in messages[0]["content"]
    assert "Conversation is the product." in messages[0]["content"]
    assert "The Brain owns data access" in messages[0]["content"]
    assert "# Canonical runtime contract v2.0" in messages[0]["content"]
    assert "Available tools:" in messages[0]["content"]
    assert "Return only the user-facing reply" in messages[0]["content"]
    assert "Conversation summary:" in messages[1]["content"]
    assert "Relevant approved memory:" in messages[1]["content"]
    assert "<untrusted_context>" in messages[1]["content"]


def test_clean_user_facing_reply_strips_backend_metadata():
    assert (
        _clean_user_facing_reply(
            """
            reply: I hear you. Let's stay with what you meant.
            mode: companion
            emotion: neutral
            should_create_task: false
            """
        )
        == "I hear you. Let's stay with what you meant."
    )


def test_clean_user_facing_reply_extracts_json_reply_only():
    assert (
        _clean_user_facing_reply(
            '{"reply":"I hear you clearly now.","mode":"companion","suggested_actions":[]}'
        )
        == "I hear you clearly now."
    )


@pytest.mark.asyncio
async def test_generate_companion_response_includes_only_approved_relevant_memories():
    now = datetime.now(UTC)
    memories = [
        {
            "title": "Qring win",
            "content": "Closed first Qring estate customer.",
            "approval_status": "approved",
            "user_approved": True,
            "importance": 9,
            "confidence": 0.9,
            "created_at": now,
        },
        {
            "title": "Pending Qring concern",
            "content": "This should not be injected.",
            "approval_status": "pending",
            "user_approved": False,
            "importance": 10,
            "confidence": 0.4,
            "created_at": now,
        },
        {
            "title": "Expired Qring note",
            "content": "Expired memory should not be injected.",
            "approval_status": "approved",
            "user_approved": True,
            "importance": 10,
            "confidence": 0.9,
            "expires_at": now - timedelta(days=1),
        },
    ]
    result, messages = await _call_service("How is Qring going?", memories=memories)

    user_prompt = messages[1]["content"]
    assert "Qring win" in user_prompt
    assert "Pending Qring concern" not in user_prompt
    assert "Expired Qring note" not in user_prompt
    assert result["memory_suggestions"]


@pytest.mark.asyncio
async def test_generate_companion_response_caps_context_at_ten_items():
    memories = [
        {
            "title": f"Qring memory {index}",
            "content": "Relevant Qring sales context.",
            "approval_status": "approved",
            "user_approved": True,
            "importance": 5,
            "confidence": 0.8,
        }
        for index in range(20)
    ]
    result, messages = await _call_service("What should I do about Qring sales?", memories=memories)

    assert len(result["context_items_used"]) <= 10
    memory_lines = [
        line for line in messages[1]["content"].splitlines()
        if line.startswith("- Qring memory")
    ]
    assert len(memory_lines) <= 10


@pytest.mark.asyncio
async def test_context_ranking_prefers_relevance_and_source_diversity():
    memories = [
        {
            "title": f"Qring sales memory {index}",
            "content": "Qring sales estate customer context.",
            "approval_status": "approved",
            "user_approved": True,
            "importance": 10,
            "confidence": 0.95,
        }
        for index in range(12)
    ]
    result, _messages = await _call_service(
        "What should I do about Qring sales?",
        memories=memories,
    )

    context = result["context_items_used"]
    assert len([item for item in context if item["source"] == "memory"]) <= 4
    assert any(item["source"] == "goal" for item in context)
    assert any(item["source"] == "project" for item in context)
    assert all("score" in item for item in context)


@pytest.mark.asyncio
async def test_emotional_messages_do_not_immediately_create_tasks():
    result, _messages = await _call_service("I'm exhausted and stressed about Qring.")

    assert result["mode"] == "companion"
    assert result["emotion"]["emotion"] in {"burned_out", "anxious", "frustrated"}
    assert result["should_create_task"] is False
    assert all(action["type"] != "create_task" for action in result["suggested_actions"])


@pytest.mark.asyncio
async def test_task_creation_only_when_user_clearly_asks():
    emotional, _ = await _call_service("I feel like I have too much to do.")
    explicit, _ = await _call_service("Create a task to call Stephen tomorrow.")

    assert emotional["should_create_task"] is False
    assert explicit["should_create_task"] is True
    assert any(action["type"] == "create_task" for action in explicit["suggested_actions"])


@pytest.mark.asyncio
async def test_validated_structured_response_is_used_when_safe():
    result, _messages = await _call_service_with_reply(
        "Create a task to call Stephen tomorrow.",
        """
        {
          "reply": "That makes sense. I can turn that into a task after you confirm.",
          "mode": "assistant",
          "should_create_task": true,
          "suggested_actions": [
            {
              "type": "create_task",
              "label": "Create task",
              "description": "Call Stephen tomorrow.",
              "requires_confirmation": true
            }
          ],
          "memory_suggestions": []
        }
        """,
    )

    assert result["reply"].startswith("That makes sense")
    assert result["mode"] == "assistant"
    assert result["should_create_task"] is True
    assert any(action["type"] == "create_task" for action in result["suggested_actions"])


@pytest.mark.asyncio
async def test_structured_task_creation_is_overridden_without_clear_user_intent():
    result, _messages = await _call_service_with_reply(
        "I'm exhausted and overwhelmed.",
        """
        {
          "reply": "That sounds heavy. Let's slow it down first.",
          "mode": "assistant",
          "should_create_task": true,
          "suggested_actions": [
            {
              "type": "create_task",
              "label": "Create task",
              "description": "Unsafe model suggestion.",
              "requires_confirmation": false
            }
          ],
          "memory_suggestions": []
        }
        """,
    )

    assert result["reply"].startswith("That sounds heavy")
    assert result["should_create_task"] is False
    assert all(action["type"] != "create_task" for action in result["suggested_actions"])


@pytest.mark.asyncio
async def test_generate_companion_response_returns_required_shape():
    result, _messages = await _call_service("Should I focus on Qring or CampusCart?")

    assert set(result) >= {
        "reply",
        "mode",
        "emotion",
        "suggested_actions",
        "should_create_task",
        "memory_suggestions",
    }
    assert isinstance(result["reply"], str)
    assert isinstance(result["emotion"], dict)
    assert isinstance(result["suggested_actions"], list)
    assert isinstance(result["memory_suggestions"], list)
