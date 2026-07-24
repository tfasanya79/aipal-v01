from __future__ import annotations

import random
from datetime import datetime


def daily_morning_greeting(name: str) -> tuple[str, str]:
    return f"Good morning, {name}.", "What should we plan for today? Tell me your tasks and I'll track them."


def daily_evening_prompt(name: str, total: int, done: int, open_count: int) -> tuple[str, str]:
    if total == 0:
        prompt = "You had a quiet day. Want to set a light plan for tomorrow?"
    else:
        prompt = f"You finished {done} of {total} tasks today. Want to carry {open_count} open items to tomorrow?"
    return f"Good evening, {name}.", prompt


def checkin_prompt(name: str) -> tuple[str, str]:
    return f"Hey {name},", "Just checking in — how are you feeling?"


def live_greeting_text(
    *,
    name: str,
    hour: int,
    in_live: bool,
    wake_hint: str | None = None,
    has_chatted_today: bool = False,
    pending_items: list[str] | None = None,
    up_next: str | None = None,
) -> str:
    text: str
    if has_chatted_today and in_live:
        text = f"I'm listening, {name}."
    elif has_chatted_today and pending_items:
        items = ", ".join(pending_items[:3])
        text = f"Welcome back, {name}. You have a plan waiting: {items}. Want to add it to Today or talk through something else?"
    elif has_chatted_today and up_next:
        text = (
            f"Hi {name}, your next up is {up_next}. Tell me what changed or what to tackle first."
            if in_live
            else f"Hi {name}, your next up is {up_next}. Go Live when you're ready, or tell me what changed."
        )
    elif has_chatted_today:
        text = f"Hi {name}, I'm here. What would you like to focus on next?"
    elif hour < 12:
        text = f"Good morning, {name}. What should we plan for today?"
    elif hour < 17:
        text = f"Hey {name}, how's your day going? Want to adjust your plan?"
    else:
        text = f"Evening, {name}. Want to reflect for a minute or plan what matters next?"
    if wake_hint and in_live:
        return f"{wake_hint} {text}"
    return text


def task_nudge_text(name: str, title: str, minutes: int) -> str:
    templates = (
        "Hi {name}, {minutes} minutes to {title} — hope you're ready.",
        "Hey {name}, {title} is in about {minutes} minutes.",
        "{name}, just a heads up — {minutes} minutes until {title}.",
        "Hi {name}, coming up: {title} in {minutes} minutes.",
    )
    return random.choice(templates).format(name=name, minutes=minutes, title=title)


def current_hour(timezone_now: datetime) -> int:
    return timezone_now.hour
