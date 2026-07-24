from __future__ import annotations


def summarize_business_context(title: str, content: str | None = None) -> str:
    return f"{title}: {(content or '').strip()[:180]}".strip(": ")[:240]
