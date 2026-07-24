"""Shared turn context helpers for REST and Live Voice v2."""

from __future__ import annotations

from ..schemas import PlanDraftResponse, ProposedTask

EMPTY_PLAN = {"intent": "other", "proposed_tasks": [], "clarifying_question": None}


def draft_to_schema(payload: dict | None) -> PlanDraftResponse | None:
    if not payload or not payload.get("proposed_tasks"):
        return None
    return PlanDraftResponse(
        intent=payload.get("intent", "plan_day"),
        proposed_tasks=[ProposedTask(**t) for t in payload["proposed_tasks"]],
        clarifying_question=payload.get("clarifying_question"),
    )


def draft_mentioned_in_history(history: list[dict[str, str]]) -> bool:
    for h in history:
        if h["role"] != "assistant":
            continue
        lower = h["content"].lower()
        if "plan draft" in lower or "plan waiting" in lower:
            return True
        if "add" in lower and "today" in lower and ("want" in lower or "shall" in lower):
            return True
    return False


def build_system_ctx(
    *,
    wake: str,
    about_me: str | None,
    local_day,
    today_snap,
    mem_block: str,
    tool_actions: list[str],
    pending: dict | None,
    extracted: dict,
    history: list[dict[str, str]],
) -> str:
    system_ctx = f"User wake name: {wake}. About: {about_me or ''}"
    open_count = today_snap.summary.open
    if today_snap.up_next:
        system_ctx += (
            f"\nToday ({local_day.isoformat()}): {open_count} open task(s). "
            f"Up next: {today_snap.up_next.title}."
        )
    else:
        system_ctx += f"\nToday ({local_day.isoformat()}): {open_count} open task(s). No up-next scheduled."
    if mem_block:
        system_ctx += f"\nMemories:\n{mem_block}"
    if tool_actions:
        system_ctx += f"\nTool results: {'; '.join(tool_actions)}"
    if pending and pending.get("proposed_tasks") and not draft_mentioned_in_history(history):
        tasks_desc = "; ".join(
            f"{t['title']}" + (f" at {t['due_at']}" if t.get("due_at") else "")
            for t in pending["proposed_tasks"]
        )
        system_ctx += (
            f"\nPending plan draft (awaiting user confirm): {tasks_desc}. "
            "Mention once if helpful; do not repeat if user already declined or confirmed."
        )
    if extracted.get("clarifying_question"):
        system_ctx += f"\nClarify: {extracted['clarifying_question']}"
    return system_ctx
