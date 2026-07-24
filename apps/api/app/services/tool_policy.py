from __future__ import annotations

_ALLOWED_BY_MODE = {
    "companion": {"reflect", "life_area_checkin", "view_tasks", "commitment_follow_up"},
    "coach": {"reflect", "life_area_checkin", "view_tasks", "review_decision", "create_growth_plan", "track_habit", "accountability_checkin", "apply_framework", "commitment_follow_up"},
    "planner": {"review_plan", "life_area_checkin", "view_tasks", "complete_task", "create_growth_plan", "accountability_checkin"},
    "assistant": {"create_task", "life_area_checkin", "view_tasks", "complete_task"},
    "reflection": {"reflect", "life_area_checkin", "view_tasks", "commitment_follow_up"},
}


def is_tool_allowed(mode: str, action_type: str, source: str | None = None) -> bool:
    allowed = _ALLOWED_BY_MODE.get((mode or "").lower(), {"life_area_checkin"})
    if action_type in allowed:
        return True
    if source == "voice" and action_type == "create_task" and mode == "assistant":
        return True
    return False
