from datetime import date
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.services import suggest_day as suggest_day_svc


def test_template_fallback_plan_day():
    result = suggest_day_svc._template_fallback("plan_day", [], date(2026, 6, 10), ZoneInfo("UTC"))
    assert result["intent"] == "plan_day"
    assert len(result["proposed_tasks"]) >= 3
    assert result["proposed_tasks"][0]["title"]


def test_template_fallback_from_open_tasks():
    class Task:
        def __init__(self, title):
            self.title = title
            self.estimated_minutes = 25
            self.priority = 2
            self.category = "work"

    result = suggest_day_svc._template_fallback(None, [Task("Email client")], date(2026, 6, 10), ZoneInfo("UTC"))
    assert len(result["proposed_tasks"]) == 1
    assert "Email client" in result["proposed_tasks"][0]["title"]
    assert result["proposed_tasks"][0]["due_at"] is not None


@pytest.mark.asyncio
async def test_suggest_day_uses_fallback_when_llm_empty():
    class User:
        id = "00000000-0000-0000-0000-000000000001"
        about_me = None
        wake_name = "Sam"
        display_name = "Sam"
        timezone = "UTC"

    empty_plan = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}

    with (
        patch("app.services.suggest_day.task_svc.list_tasks", new_callable=AsyncMock, return_value=[]),
        patch("app.services.suggest_day.plan_extractor.extract_plan", new_callable=AsyncMock, return_value=empty_plan),
        patch("app.services.suggest_day.draft_svc.save_draft", new_callable=AsyncMock) as save_draft,
    ):
        result = await suggest_day_svc.suggest_day(AsyncMock(), User(), template="break")

    assert result["proposed_tasks"]
    save_draft.assert_awaited_once()
    assert save_draft.await_args.args[2]["proposed_tasks"]
