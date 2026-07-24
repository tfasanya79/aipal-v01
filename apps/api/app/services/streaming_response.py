"""Bounded text segmentation primitives for incremental spoken responses."""

from __future__ import annotations

import re

_BOUNDARY = re.compile(r"[.!?;:\n,]")


class SpeechSegmenter:
    """Emit speech-safe clauses without waiting for complete sentences."""

    def __init__(self, *, min_chars: int = 28, max_chars: int = 120) -> None:
        if min_chars < 8 or max_chars <= min_chars:
            raise ValueError("Speech segment bounds are invalid")
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    @property
    def buffered_text(self) -> str:
        return self._buffer

    def push(self, chunk: str) -> list[str]:
        if not chunk:
            return []
        self._buffer += chunk
        segments: list[str] = []
        while self._buffer:
            boundary = self._boundary_index()
            if boundary is not None:
                segment = self._take(boundary + 1)
                if segment:
                    segments.append(segment)
                continue
            if len(self._buffer) < self.max_chars:
                break
            split = self._buffer.rfind(" ", self.min_chars, self.max_chars + 1)
            if split < self.min_chars:
                split = self.max_chars
            segment = self._take(split)
            if segment:
                segments.append(segment)
        return segments

    def flush(self) -> list[str]:
        segment = self._buffer.strip()
        self._buffer = ""
        return [segment] if segment else []

    def _boundary_index(self) -> int | None:
        for match in _BOUNDARY.finditer(self._buffer):
            length = match.end()
            punctuation = match.group(0)
            minimum = max(self.min_chars, 28) if punctuation == "," else self.min_chars
            if length >= minimum:
                return match.start()
        return None

    def _take(self, end: int) -> str:
        segment = self._buffer[:end].strip()
        self._buffer = self._buffer[end:].lstrip()
        return segment
