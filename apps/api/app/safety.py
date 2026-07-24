import json
from pathlib import Path

CRISIS_KEYWORDS = (
    "kill myself",
    "suicide",
    "end my life",
    "self-harm",
    "hurt myself",
    "want to die",
)


def is_crisis_likely(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in CRISIS_KEYWORDS)


def crisis_reply(resources_path: Path | None = None) -> str:
    body = (
        "I'm really glad you told me. You're not alone. "
        "Please reach out to someone you trust or a crisis line right now. "
        "If you're in immediate danger, call your local emergency number."
    )
    if resources_path and resources_path.is_file():
        try:
            data = json.loads(resources_path.read_text(encoding="utf-8"))
            parts = [str(data.get("disclaimer", "")).strip(), ""]
            for r in data.get("resources", []):
                parts.append(f"• {r.get('name', '')} — {r.get('phone', '')} {r.get('url', '')}".strip())
            body = "\n".join(p for p in parts if p)
        except (json.JSONDecodeError, OSError):
            pass
    return body
