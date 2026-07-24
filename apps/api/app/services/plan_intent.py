import re

_CONFIRM_PATTERNS = (
    r"^(yes|yeah|yep|sure|ok|okay|please do|sounds good|go ahead|add it|add them|"
    r"add to today|put it on today|confirm|do it|that works)\b",
    r"\b(yes add|add that|add those|add to today)\b",
)


def is_confirm_intent(text: str) -> bool:
    """True when user is approving a pending plan draft."""
    t = text.lower().strip()
    if not t:
        return False
    return any(re.search(p, t) for p in _CONFIRM_PATTERNS)


def is_discard_intent(text: str) -> bool:
    t = text.lower().strip()
    return bool(
        re.search(
            r"^(no|nope|not now|skip|cancel|don't add|do not add|never mind|nevermind)\b",
            t,
        )
    )
