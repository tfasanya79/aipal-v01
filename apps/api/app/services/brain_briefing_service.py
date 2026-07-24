from __future__ import annotations

import hashlib
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import User
from .companion_orchestrator import run_turn as run_companion_turn
from .context_cache import get_context_cache, set_context_cache


def _clip_items(items: Iterable[object], limit: int = 10) -> list[str]:
    clipped: list[str] = []
    for item in items:
        if len(clipped) >= limit:
            break
        text = str(item).strip()
        if text:
            clipped.append(text[:500])
    return clipped


async def _brief(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    source: str,
) -> dict[str, object]:
    result = await run_companion_turn(db, user, message, source=source)
    return {
        "message": str(result.get("reply") or "").strip(),
        "mode": result.get("mode") or "companion",
        "emotion": result.get("emotion") or {"emotion": "neutral", "intensity": 1},
        "source": "brain",
        "conversation_id": result.get("conversation_id"),
    }


def _briefing_cache_id(kind: str, message: str) -> str:
    digest = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
    return f"briefing:{kind}:{digest}"


async def _cached_brief(
    db: AsyncSession,
    user: User,
    message: str,
    *,
    source: str,
    cache_kind: str | None = None,
) -> dict[str, object]:
    if cache_kind:
        cache_id = _briefing_cache_id(cache_kind, message)
        cached = await get_context_cache(str(user.id), cache_id)
        if cached and isinstance(cached.get("message"), str):
            cached["cache"] = "hit"
            return cached
    result = await _brief(db, user, message, source=source)
    if cache_kind:
        result["cache"] = "miss"
        await set_context_cache(str(user.id), _briefing_cache_id(cache_kind, message), result)
    return result


async def generate_today_briefing(
    db: AsyncSession,
    user: User,
    *,
    user_message: str | None = None,
) -> dict[str, object]:
    name = user.wake_name or user.display_name or "friend"
    prompt = user_message or (
        f"Create a warm, concise Today briefing for {name}. "
        "Use my current tasks, reminders, commitments, goals, and recent context. "
        "Do not invent details. Keep it natural and action-light."
    )
    return await _cached_brief(db, user, prompt, source="brain_today_briefing", cache_kind="today")


async def generate_goal_briefing(
    db: AsyncSession,
    user: User,
    *,
    user_message: str | None = None,
) -> dict[str, object]:
    prompt = user_message or (
        "Explain my active goals this week in a warm companion voice. "
        "Mention only evidence-backed priorities and one useful next thought."
    )
    return await _cached_brief(db, user, prompt, source="brain_goal_briefing", cache_kind="goals")


async def generate_task_briefing(
    db: AsyncSession,
    user: User,
    *,
    user_message: str | None = None,
) -> dict[str, object]:
    prompt = user_message or (
        "Give me a friendly plan from my current tasks. "
        "Help me understand what matters today without sounding like a task scheduler."
    )
    return await _cached_brief(db, user, prompt, source="brain_task_briefing", cache_kind="tasks")


async def generate_notification_briefing(
    db: AsyncSession,
    user: User,
    *,
    user_message: str | None = None,
    trigger_context: str | None = None,
) -> dict[str, object]:
    prompt = user_message or (
        "Turn this notification or nudge context into a gentle companion check-in. "
        "Do not shame me. Keep it short and human."
    )
    if trigger_context:
        prompt = f"{prompt}\n\nNotification context: {trigger_context[:1000]}"
    return await _brief(db, user, prompt, source="brain_notification_briefing")


async def generate_connector_briefing(
    db: AsyncSession,
    user: User,
    *,
    source_type: str,
    items: Iterable[object] = (),
    user_message: str | None = None,
) -> dict[str, object]:
    evidence = _clip_items(items, limit=10)
    prompt = user_message or (
        f"Brief me on the important {source_type} context. "
        "Summarize commitments, follow-ups, and anything worth my attention. "
        "Do not include raw private content; use only concise summaries."
    )
    if evidence:
        prompt = f"{prompt}\n\nCapped {source_type} evidence:\n" + "\n".join(f"- {item}" for item in evidence)
    return await _brief(db, user, prompt, source=f"brain_connector_{source_type}_briefing")


async def generate_insight_briefing(
    db: AsyncSession,
    user: User,
    *,
    insight_type: str,
    metrics: dict[str, object],
) -> dict[str, object]:
    summary = metrics.get("summary") if isinstance(metrics.get("summary"), dict) else {}
    growth = metrics.get("growth") if isinstance(metrics.get("growth"), dict) else {}
    business = metrics.get("business") if isinstance(metrics.get("business"), dict) else {}
    top_areas = metrics.get("top_areas") if isinstance(metrics.get("top_areas"), list) else []
    evidence = [
        f"Insight type: {insight_type}",
        f"Sparse data: {metrics.get('sparse')}",
        f"Summary metrics: {summary}",
        f"Business metrics: {business}",
        f"Growth signals: {growth}",
        f"Top life areas: {top_areas[:3]}",
    ]
    prompt = (
        "Turn these grounded AiPal insight metrics into a warm, concise companion summary. "
        "Only reference evidence in the metrics. Do not invent details. "
        "Use one or two natural sentences, then one gentle next thought if useful.\n\n"
        + "\n".join(str(item)[:700] for item in evidence)
    )
    return await _cached_brief(db, user, prompt, source=f"brain_{insight_type}_insight", cache_kind=f"insight_{insight_type}")


async def generate_life_map_briefing(
    db: AsyncSession,
    user: User,
    *,
    life_map: dict[str, object],
    life_area: str | None = None,
) -> dict[str, object]:
    areas = life_map.get("areas") if isinstance(life_map.get("areas"), list) else []
    if not areas and life_area:
        areas = [life_map]
    evidence: list[str] = []
    for area in areas[:7]:
        if not isinstance(area, dict):
            continue
        evidence.append(
            (
                f"{area.get('label') or area.get('life_area')}: "
                f"progress={area.get('progress')}, "
                f"goals={area.get('goal_count')}, tasks={area.get('task_count')}, "
                f"habits={area.get('habit_count')}, memories={area.get('memory_count')}, "
                f"wins={area.get('win_count')}, challenges={area.get('challenge_count')}, "
                f"suggested_for_review={area.get('suggested_count')}"
            )
        )
    prompt = (
        "Turn this grounded AiPal Life Map into warm companion prose. "
        "Only mention the evidence provided. Do not invent events, diagnoses, or private details. "
        "Keep it to two short sentences and one gentle next thought if useful.\n\n"
        f"Sparse data: {life_map.get('sparse')}\n"
        + "\n".join(evidence)
    )
    cache_kind = f"life_map_{life_area}" if life_area else "life_map"
    return await _cached_brief(db, user, prompt, source="brain_life_map_briefing", cache_kind=cache_kind)


async def generate_proactive_prompt_wording(
    db: AsyncSession,
    user: User,
    *,
    trigger_type: str,
    context: str,
) -> dict[str, object]:
    prompt = (
        "Create one gentle proactive companion sentence from this structured trigger. "
        "Do not be generic. Do not overstep. If it is not useful, keep it very light.\n\n"
        f"Trigger type: {trigger_type}\nContext: {context[:1000]}"
    )
    return await _brief(db, user, prompt, source="brain_proactive_wording")
