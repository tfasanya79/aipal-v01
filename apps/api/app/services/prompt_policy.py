from __future__ import annotations

import re

_INJECTION_PATTERNS = (
    r"ignore (all|any|previous) instructions",
    r"disregard (all|any|previous) instructions",
    r"system prompt",
    r"developer message",
    r"tool call",
    r"hidden instructions",
    r"act as",
)


def contains_prompt_injection(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(pattern, lower) for pattern in _INJECTION_PATTERNS)


def sanitize_untrusted_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    for pattern in _INJECTION_PATTERNS:
        cleaned = re.sub(pattern, "[redacted]", cleaned, flags=re.IGNORECASE)
    return cleaned
