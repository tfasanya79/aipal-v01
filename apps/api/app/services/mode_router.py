from __future__ import annotations

from collections.abc import Iterable

_REFLECTION_WORDS = (
    "reflection",
    "reflect",
    "journal",
    "review",
    "wins",
    "lessons",
    "mood",
    "gratitude",
    "what did i learn",
    "what did i do",
    "how did today go",
    "end of day",
    "daily review",
)

_PLANNER_WORDS = (
    "plan my day",
    "plan my week",
    "organize tomorrow",
    "organize my day",
    "schedule",
    "build a plan",
    "make a plan",
    "30 day",
    "60 day",
    "90 day",
    "growth plan",
)

_ASSISTANT_WORDS = (
    "add ",
    "remind me",
    "create task",
    "create a task",
    "set a reminder",
    "start focus",
    "import calendar",
)

_COACH_WORDS = (
    "what should i do",
    "should i",
    "help me decide",
    "help me think",
    "what is the best",
    "should i focus",
    "which should i",
    "i'm stuck",
    "i am stuck",
    "can't decide",
    "cant decide",
    "which one",
    "opportunity cost",
    "tradeoff",
    "strategy",
    "first principles",
    "swot",
    "decision matrix",
    "risk reward",
    "keep saying",
    "accountability",
    "habit",
)

_HABIT_WORDS = (
    "every morning",
    "every day",
    "again today",
    "again this week",
    "prayed",
    "praying",
    "prayer",
    "gym",
    "exercise",
    "reading",
    "meditation",
    "sales calls",
)

_COMPANION_WORDS = (
    "i feel",
    "i'm feeling",
    "im feeling",
    "i'm worried",
    "im worried",
    "i'm tired",
    "im tired",
    "i'm frustrated",
    "im frustrated",
    "i'm anxious",
    "im anxious",
    "i just need to talk",
)


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def _looks_like_coaching_query(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in ("?", "what", "how", "should", "help", "which", "stuck", "focus on", "keep saying"))


def classify_mode(message: str, emotion: str, recent_context: str | None = None) -> str:
    text = (message or "").strip().lower()
    context = (recent_context or "").lower()

    if _contains_any(text, _REFLECTION_WORDS) or _contains_any(context, _REFLECTION_WORDS):
        return "reflection"
    if _contains_any(text, _PLANNER_WORDS):
        return "planner"
    if _contains_any(text, _ASSISTANT_WORDS):
        return "assistant"
    if _contains_any(text, _COACH_WORDS) and (
        _contains_any(text, ("should i", "help me decide", "help me think", "what should i", "i'm stuck", "i am stuck", "can't decide", "cant decide", "keep saying", "accountability"))
        or (_contains_any(text, ("strategy", "habit")) and _looks_like_coaching_query(text))
    ):
        return "coach"
    if _contains_any(text, _HABIT_WORDS) and _looks_like_coaching_query(text):
        return "coach"
    if _contains_any(text, _COMPANION_WORDS):
        return "companion"

    if emotion in {"confused", "frustrated", "sad", "burned_out", "anxious"}:
        return "companion"
    if emotion in {"happy", "excited"} and len(text.split()) <= 10:
        return "companion"
    return "companion"
