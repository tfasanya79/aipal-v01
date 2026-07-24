from __future__ import annotations


def summarize_calendar_item(title: str, attendees: list[str] | None = None) -> str:
    people = ", ".join(attendees or [])
    if people:
        return f"{title} with {people}"[:240]
    return title[:240]

