from __future__ import annotations


def summarize_document_item(title: str, content: str | None = None) -> str:
    body = content.strip() if content else ""
    return f"{title}: {body[:180]}".strip(": ")[:240]

