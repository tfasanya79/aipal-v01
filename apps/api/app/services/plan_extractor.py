import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_PLAN_SIGNAL = re.compile(
    r"\b(remind|add|plan|schedule|meeting|tomorrow|next week|next month|need to|going to|i'll|i will|swim|bed|gym|at\s+\d|\d{1,2}\s*(?:am|pm)|\d{1,2}:\d{2})\b",
    re.IGNORECASE,
)
_COMPLETE_SIGNAL = re.compile(
    r"\b(finished|completed|done with|already did|mark .+ done)\b",
    re.IGNORECASE,
)


def needs_plan_extraction(text: str) -> bool:
    """Skip the extra LLM call unless the utterance may involve planning or completion."""
    t = text.strip()
    if not t:
        return False
    return bool(_PLAN_SIGNAL.search(t) or _COMPLETE_SIGNAL.search(t))

def _compact_title(title: str, notes: str | None = None) -> tuple[str, str | None]:
    cleaned = " ".join(title.strip().split())
    words = cleaned.split()
    if len(words) <= 4:
        compact = cleaned.title() if cleaned.islower() or cleaned.isupper() else cleaned
        return compact[:80], notes
    short = " ".join(words[:4])
    short = short.title() if short.islower() else short
    overflow = " ".join(words[4:])
    merged_notes = f"{overflow}. {notes}".strip(". ") if notes else overflow
    return short[:80], merged_notes[:500] if merged_notes else None


def _heuristic_title(phrase: str) -> str:
    p = phrase.lower().strip()
    if "bed" in p or "sleep" in p:
        return "Bedtime"
    if "swim" in p:
        return "Swimming"
    if "meet" in p:
        return "Meeting"
    if "gym" in p or "workout" in p:
        return "Workout"
    if "eat" in p or "lunch" in p or "dinner" in p:
        return "Meal"
    words = p.split()
    if len(words) <= 4:
        return phrase.strip().title()
    return " ".join(words[-4:]).title()


def _category_for(phrase: str) -> str:
    lower = phrase.lower()
    if any(word in lower for word in ("meeting", "client", "customer", "invoice", "sales", "demo", "investor", "work")):
        return "work"
    if any(word in lower for word in ("gym", "workout", "swim", "run", "sleep", "bed", "doctor", "health")):
        return "health"
    if any(word in lower for word in ("home", "clean", "cook", "laundry")):
        return "home"
    return "personal"


def _priority_for(phrase: str) -> int:
    lower = phrase.lower()
    if any(word in lower for word in ("urgent", "important", "must", "deadline", "investor", "demo")):
        return 2
    if any(word in lower for word in ("maybe", "sometime", "if i can")):
        return 0
    return 1


def _date_for_relative(text: str, today: date) -> date:
    lower = text.lower()
    if "next month" in lower:
        return today + timedelta(days=30)
    if "next week" in lower:
        return today + timedelta(days=7)
    if "tomorrow" in lower:
        return today + timedelta(days=1)
    return today


def _extract_time(text: str) -> tuple[int, int] | None:
    if match := re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.IGNORECASE):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        ampm = match.group(3).lower()
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        return hour, minute
    if match := re.search(r"\b(?:at|by)\s+(\d{1,2})(?::(\d{2}))?\b", text, re.IGNORECASE):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        return hour, minute
    return None


def _task_from_phrase(phrase: str, *, source_text: str, today: date, tz: ZoneInfo) -> dict:
    target_date = _date_for_relative(source_text, today)
    time_parts = _extract_time(source_text)
    due_at = None
    if time_parts is not None:
        due_at = datetime(target_date.year, target_date.month, target_date.day, time_parts[0], time_parts[1], tzinfo=tz)
    elif target_date != today:
        due_at = datetime(target_date.year, target_date.month, target_date.day, 9, 0, tzinfo=tz)
    title = _heuristic_title(phrase)
    return {
        "title": title,
        "notes": phrase[:500],
        "due_at": due_at.isoformat() if due_at else None,
        "estimated_minutes": 60 if _category_for(phrase) == "work" else 30,
        "priority": _priority_for(source_text),
        "category": _category_for(phrase),
    }


async def extract_plan(
    user_message: str,
    *,
    wake_name: str,
    timezone: str,
    history_summary: str = "",
    today: date | None = None,
) -> dict:
    today = today or date.today()
    try:
        tz = ZoneInfo(timezone or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")

    return _regex_fallback(user_message, today, tz)


def _normalize_plan(raw: dict, today: date, tz: ZoneInfo, user_message: str = "") -> dict:
    intent = raw.get("intent") or "other"
    tasks = raw.get("proposed_tasks") or []
    if not isinstance(tasks, list):
        tasks = []
    normalized = []
    for t in tasks[:8]:
        if not isinstance(t, dict) or not t.get("title"):
            continue
        due = t.get("due_at")
        if due and isinstance(due, str):
            try:
                due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=tz)
            except ValueError:
                due_dt = None
        else:
            due_dt = None
        notes = t.get("notes")
        title, notes = _compact_title(str(t["title"]), str(notes) if notes else None)
        if not notes and user_message and len(str(t["title"])) > len(title) + 5:
            notes = str(t["title"])[:500]
        normalized.append(
            {
                "title": title,
                "notes": notes,
                "due_at": due_dt.isoformat() if due_dt else None,
                "estimated_minutes": int(t.get("estimated_minutes") or 30),
                "priority": min(3, max(0, int(t.get("priority", 1)))),
                "category": t.get("category"),
            }
        )
    return {
        "intent": intent,
        "proposed_tasks": normalized,
        "clarifying_question": raw.get("clarifying_question"),
    }


def _regex_fallback(user_message: str, today: date, tz: ZoneInfo) -> dict:
    """Lightweight fallback when LLM JSON fails."""
    tasks = []
    patterns = [
        re.compile(
            r"(?:remind(?:\s+me)?\s+(?:to\s+)?|add\s+(?:a\s+)?)([\w\s]{2,50}?)\s+(?:at|by)\s+"
            r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            re.IGNORECASE,
        ),
        re.compile(
            r"(\w[\w\s]{2,40}?)\s+(?:at|by)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
            re.IGNORECASE,
        ),
    ]
    seen = set()
    for pattern in patterns:
        for m in pattern.finditer(user_message):
            phrase = m.group(1).strip()
            hour = int(m.group(2))
            minute = int(m.group(3) or 0)
            ampm = (m.group(4) or "").lower()
            if ampm == "pm" and hour < 12:
                hour += 12
            if ampm == "am" and hour == 12:
                hour = 0
            due_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=tz)
            title = _heuristic_title(phrase)
            key = (title.lower(), due_dt.isoformat())
            if key in seen:
                continue
            seen.add(key)
            tasks.append(
                _task_from_phrase(phrase, source_text=user_message, today=today, tz=tz)
                | {"due_at": due_dt.isoformat(), "title": title}
            )
    commitment_patterns = [
        re.compile(
            r"(?:i\s+(?:need|plan|want)\s+to|i(?:'ll| will| am going to)|tomorrow\s+i(?:'ll| will| need to))\s+(.+?)(?:\s+(?:tomorrow|next week|next month|today))?$",
            re.IGNORECASE,
        ),
        re.compile(r"(?:remind me to|add|schedule)\s+(.+?)(?:\s+(?:tomorrow|next week|next month|today))?$", re.IGNORECASE),
    ]
    for pattern in commitment_patterns:
        match = pattern.search(user_message)
        if not match:
            continue
        phrase = re.sub(r"\s+(?:at|by)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", "", match.group(1), flags=re.IGNORECASE)
        parts = [part.strip(" .") for part in re.split(r"\s+(?:and then|then|and)\s+|,", phrase) if part.strip(" .")]
        for part in parts[:6]:
            task = _task_from_phrase(part, source_text=user_message, today=today, tz=tz)
            key = (task["title"].lower(), task["due_at"])
            if key in seen:
                continue
            seen.add(key)
            tasks.append(task)
    return {
        "intent": "plan_day" if tasks else "other",
        "proposed_tasks": tasks,
        "clarifying_question": None,
    }
