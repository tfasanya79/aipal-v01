"""Live Voice v2 helpers: sentence splitting, turn cancellation, rate limits."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import AsyncIterator

log = logging.getLogger("aipal.voice_pipeline")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_PLAN_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def split_sentences(text: str, *, flush: bool = False) -> tuple[list[str], str]:
    """Return complete sentences and trailing remainder."""
    if flush and text.strip():
        return [text.strip()], ""
    parts = _SENTENCE_SPLIT.split(text)
    if len(parts) <= 1:
        return [], text
    complete = [p.strip() for p in parts[:-1] if p.strip()]
    return complete, parts[-1]


def strip_plan_json_block(text: str) -> tuple[str, str | None]:
    """Remove trailing plan JSON fenced block; return (visible_text, json_str)."""
    match = _PLAN_JSON_BLOCK.search(text)
    if not match:
        return text, None
    visible = text[: match.start()].rstrip()
    return visible, match.group(1)


@dataclass(slots=True)
class _TurnHandle:
    task: asyncio.Task
    cancel_event: asyncio.Event


class TurnCancellationRegistry:
    """Per-connection registry of in-flight turn tasks by turn_id."""

    def __init__(self) -> None:
        self._turns: dict[str, _TurnHandle] = {}

    def register(
        self,
        turn_id: str,
        task: asyncio.Task,
        *,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        old = self._turns.pop(turn_id, None)
        if old and not old.task.done():
            old.cancel_event.set()
            old.task.cancel()
        self._turns[turn_id] = _TurnHandle(task, cancel_event or asyncio.Event())

    def cancel(self, turn_id: str) -> bool:
        handle = self._turns.pop(turn_id, None)
        if handle and not handle.task.done():
            handle.cancel_event.set()
            handle.task.cancel()
            return True
        return False

    def clear(self, turn_id: str) -> None:
        self._turns.pop(turn_id, None)

    def cancel_all(self) -> int:
        cancelled = 0
        for turn_id in list(self._turns):
            if self.cancel(turn_id):
                cancelled += 1
        return cancelled

    @property
    def has_active(self) -> bool:
        return any(not handle.task.done() for handle in self._turns.values())


class TurnRateLimiter:
    """Simple in-memory per-user turn rate limit."""

    def __init__(self, max_per_minute: int) -> None:
        self._max = max_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, user_id: str) -> bool:
        now = time.monotonic()
        window = self._hits[user_id]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= self._max:
            return False
        window.append(now)
        return True


async def stream_tts_sentences(
    text_stream: AsyncIterator[str],
    synthesize_fn,
    *,
    cancel_event: asyncio.Event | None = None,
) -> AsyncIterator[tuple[int, bytes, str]]:
    """Yield (index, audio_bytes, mime) for each completed sentence from token stream."""
    buffer = ""
    index = 0
    async for chunk in text_stream:
        if cancel_event and cancel_event.is_set():
            break
        buffer += chunk
        sentences, buffer = split_sentences(buffer)
        for sentence in sentences:
            if cancel_event and cancel_event.is_set():
                break
            audio, mime = await synthesize_fn(sentence)
            if audio:
                yield index, audio, mime
                index += 1
    if buffer.strip() and not (cancel_event and cancel_event.is_set()):
        audio, mime = await synthesize_fn(buffer.strip())
        if audio:
            yield index, audio, mime
