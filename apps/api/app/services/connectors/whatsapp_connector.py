from __future__ import annotations


def summarize_whatsapp_item(title: str, content: str | None = None) -> str:
    return f"{title}: {(content or '').strip()[:180]}".strip(": ")[:240]

