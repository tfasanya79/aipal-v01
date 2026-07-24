from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import TodayItem, User
from .brain_briefing_service import generate_today_briefing
from .memory_service import search_memories
from .next_item_helper_service import get_next_upcoming_item
from .today_item_service import list_today_items, today_item_to_dict


def _display_name(user: User) -> str:
    return user.wake_name or user.display_name or user.email.split("@", 1)[0] or "friend"


def _time_of_day(now: datetime | None = None) -> str:
    hour = (now or datetime.now(UTC)).hour
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _item_time_text(item: TodayItem | None) -> str | None:
    if item is None:
        return None
    when = item.start_time or item.due_at
    if when is None:
        return None
    return when.strftime("%-I:%M %p") if hasattr(when, "strftime") else str(when)


def _card(card_id: str, title: str, subtitle: str, prompt: str, icon: str) -> dict[str, str]:
    return {
        "id": card_id,
        "title": title,
        "subtitle": subtitle,
        "prompt": prompt,
        "icon": icon,
    }


async def get_companion_cards(db: AsyncSession, user_id) -> list[dict[str, str]]:
    next_item = await get_next_upcoming_item(db, user_id)
    next_title = next_item.title if next_item else "my next important thing"
    return [
        _card(
            "prepare_next_meeting",
            "Prepare for next meeting",
            "Get a calm recap before you go in.",
            f"Help me prepare for {next_title}.",
            "event_note",
        ),
        _card(
            "reflect_today",
            "Reflect on today",
            "A gentle evening-style check-in.",
            "Can we reflect on today together?",
            "auto_stories",
        ),
        _card(
            "start_focus",
            "Start focus",
            "Choose one thing and settle in.",
            "Help me start a focused work session.",
            "center_focus_strong",
        ),
        _card(
            "review_wins",
            "Review wins",
            "Look back at what has moved forward.",
            "Help me review my recent wins.",
            "emoji_events",
        ),
        _card(
            "talk_through",
            "Talk through something",
            "Think out loud with AiPal.",
            "I want to talk through something.",
            "forum",
        ),
        _card(
            "plan_day",
            "Plan my day",
            "Turn today into a realistic agenda.",
            "Help me plan my day.",
            "calendar_today",
        ),
    ]


async def build_companion_home_context(db: AsyncSession, user: User) -> dict[str, Any]:
    today = date.today()
    items = await list_today_items(db, user.id, today)
    next_item = await get_next_upcoming_item(db, user.id)
    memories = await search_memories(
        db,
        user.id,
        "today current emotional state wins meetings commitments projects",
        limit=3,
    )
    cards = await get_companion_cards(db, user.id)
    open_items = [item for item in items if item.status not in {"completed", "cancelled", "dismissed"}]
    if next_item is None and open_items:
        next_item = sorted(open_items, key=lambda item: item.start_time or item.due_at or item.created_at)[0]
    return {
        "name": _display_name(user),
        "time_of_day": _time_of_day(),
        "today_count": len(open_items),
        "next_item": today_item_to_dict(next_item) if next_item else None,
        "next_item_time": _item_time_text(next_item),
        "recent_context": [
            {
                "title": memory.title,
                "type": memory.type,
                "life_area": memory.life_area,
            }
            for memory in memories[:3]
        ],
        "cards": cards,
    }


def _fallback_brief(context: dict[str, Any]) -> str:
    name = context["name"]
    time_of_day = context["time_of_day"]
    next_item = context.get("next_item") or {}
    if next_item:
        when = context.get("next_item_time") or "soon"
        return f"Good {time_of_day}, {name}. Your next item is {next_item.get('title', 'something important')} at {when}. Want to prepare together?"
    count = context.get("today_count", 0)
    if count:
        return f"Good {time_of_day}, {name}. You have {count} thing{'s' if count != 1 else ''} on today. Want to sort the day together?"
    return f"Good {time_of_day}, {name}. I’m here with you. What would feel useful to talk through first?"


async def generate_companion_home_brief(db: AsyncSession, user: User) -> dict[str, Any]:
    context = await build_companion_home_context(db, user)
    next_item = context.get("next_item") or {}
    prompt = (
        "Create a warm, concise Companion home greeting. "
        "Conversation is the heart. Mention the next item only if useful. "
        "Do not invent mood, memories, meetings, or tasks. "
        "End with one gentle invitation.\n\n"
        f"User name: {context['name']}\n"
        f"Time of day: {context['time_of_day']}\n"
        f"Open Today items: {context['today_count']}\n"
        f"Next item: {next_item.get('title') or 'none'}\n"
        f"Next item time: {context.get('next_item_time') or 'none'}\n"
        f"Recent context titles: {[item['title'] for item in context['recent_context']]}"
    )
    try:
        brief = await generate_today_briefing(db, user, user_message=prompt)
        message = str(brief.get("message") or "").strip()
    except Exception:
        brief = {"source": "fallback"}
        message = ""
    if not message:
        message = _fallback_brief(context)
    return {
        "message": message,
        "source": brief.get("source", "brain"),
        "context": context,
        "cards": context["cards"],
        "status": "ok",
    }
