import logging
import os
from typing import Any

from .config import get_settings

log = logging.getLogger("aipal.memory")
_settings = get_settings()
_memory = None
_mem0_disabled_notice_logged = False
_mem0_unavailable_logged = False


def _has_mem0_credentials() -> bool:
    return any(
        os.getenv(name)
        for name in (
            "MEM0_API_KEY",
            "MEM0_ADMIN_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_ADMIN_KEY",
        )
    )


def get_memory():
    global _memory, _mem0_disabled_notice_logged, _mem0_unavailable_logged
    if not _settings.mem0_enabled:
        return None
    if not _has_mem0_credentials():
        if not _mem0_disabled_notice_logged:
            log.info(
                "Mem0 enabled but no Mem0/OpenAI credentials are configured; "
                "skipping optional Mem0 memory adapter."
            )
            _mem0_disabled_notice_logged = True
        return None
    if _memory is not None:
        return _memory
    try:
        from mem0 import Memory

        _memory = Memory()
        return _memory
    except Exception as exc:
        if not _mem0_unavailable_logged:
            log.warning("Mem0 unavailable; optional cloud memory adapter disabled: %s", exc)
            _mem0_unavailable_logged = True
        return None


def memory_add(user_id: str, text: str, metadata: dict[str, Any] | None = None) -> None:
    m = get_memory()
    if not m:
        return
    try:
        m.add(text, user_id=user_id, metadata=metadata or {})
    except Exception as exc:
        log.warning("mem0 add failed: %s", exc)


def memory_search(user_id: str, query: str, limit: int = 5) -> list[str]:
    m = get_memory()
    if not m:
        return []
    try:
        results = m.search(query, user_id=user_id, limit=limit)
        if isinstance(results, dict) and "results" in results:
            return [r.get("memory", r.get("text", "")) for r in results["results"]]
        if isinstance(results, list):
            return [str(r) for r in results]
    except Exception as exc:
        log.warning("mem0 search failed: %s", exc)
    return []


def memory_delete_user(user_id: str) -> None:
    m = get_memory()
    if not m:
        return
    try:
        m.delete_all(user_id=user_id)
    except Exception as exc:
        log.warning("mem0 delete failed: %s", exc)
