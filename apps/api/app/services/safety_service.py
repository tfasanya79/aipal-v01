from __future__ import annotations

from ..safety import crisis_reply, is_crisis_likely


def is_safe_message(message: str) -> bool:
    return not is_crisis_likely(message)


def safe_reply(message: str) -> str:
    return crisis_reply() if is_crisis_likely(message) else message
