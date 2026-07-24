from __future__ import annotations

import json
import time
from typing import Any

from ..config import get_settings

_settings = get_settings()
_memory_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_redis_client: Any | None = None
_redis_checked = False


def _cache_key(user_id: str, conversation_id: str) -> str:
    return f"aipal:context:{user_id}:{conversation_id}"


async def get_context_cache(user_id: str, conversation_id: str) -> dict[str, Any] | None:
    key = _cache_key(user_id, conversation_id)
    redis = _get_redis()
    if redis is not None:
        try:
            raw = await redis.get(key)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                return json.loads(raw)
            return None
        except Exception:
            _disable_redis()

    cached = _memory_cache.get(key)
    if cached is None:
        return None
    expires_at, value = cached
    if expires_at <= time.time():
        _memory_cache.pop(key, None)
        return None
    return value


async def set_context_cache(user_id: str, conversation_id: str, value: dict[str, Any]) -> None:
    ttl = max(30, int(_settings.context_cache_ttl_seconds))
    key = _cache_key(user_id, conversation_id)
    payload = json.dumps(value, default=str)
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.set(key, payload, ex=ttl)
            return
        except Exception:
            _disable_redis()
    _memory_cache[key] = (time.time() + ttl, json.loads(payload))
    _trim_memory_cache()


async def delete_context_cache(user_id: str, conversation_id: str) -> None:
    key = _cache_key(user_id, conversation_id)
    redis = _get_redis()
    if redis is not None:
        try:
            await redis.delete(key)
            return
        except Exception:
            _disable_redis()
    _memory_cache.pop(key, None)


def _get_redis() -> Any | None:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if not _settings.redis_url:
        return None
    try:
        from redis.asyncio import Redis

        _redis_client = Redis.from_url(_settings.redis_url, decode_responses=True)
    except Exception:
        _redis_client = None
    return _redis_client


def _disable_redis() -> None:
    global _redis_client, _redis_checked
    _redis_client = None
    _redis_checked = True


def _trim_memory_cache(max_entries: int = 512) -> None:
    if len(_memory_cache) <= max_entries:
        return
    now = time.time()
    expired = [key for key, (expires_at, _value) in _memory_cache.items() if expires_at <= now]
    for key in expired:
        _memory_cache.pop(key, None)
    if len(_memory_cache) <= max_entries:
        return
    for key in sorted(_memory_cache, key=lambda item: _memory_cache[item][0])[: len(_memory_cache) - max_entries]:
        _memory_cache.pop(key, None)
