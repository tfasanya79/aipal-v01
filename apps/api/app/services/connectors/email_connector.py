from __future__ import annotations


def summarize_email_item(subject: str, snippet: str | None = None) -> str:
    summary = subject.strip()
    if snippet:
        summary = f"{summary}: {snippet.strip()[:180]}"
    return summary[:240]

