"""Self-hosted streaming STT via faster-whisper."""

from __future__ import annotations

import asyncio
import logging
import math
import re
import threading
import time
from contextlib import suppress
from typing import Any

import numpy as np

from ..config import Settings
from ..stt import _get_model
from .stt_provider import STTFinal, STTPartial

log = logging.getLogger("aipal.whisper_stream")

# Serialize the actual synchronous model work, including work whose awaiting
# coroutine was cancelled while its worker thread was already running.
_inference_lock = threading.Lock()
_LANGUAGE_HINTS: dict[str, tuple[str, ...]] = {
    "pcm": (
        "abeg",
        "dey",
        "una",
        "wahala",
        "wetin",
        "make una",
        "leave am",
    ),
}


class WhisperStreamingSTT:
    SAMPLE_RATE = 16000

    def __init__(self, settings: Settings) -> None:
        self._partial_interval_ms = settings.whisper_stream_partial_interval_ms
        self._partial_interval_min_ms = max(80, min(self._partial_interval_ms, 180))
        self._partial_interval_max_ms = max(self._partial_interval_ms, 450)
        self._final_beam_size = max(1, int(settings.whisper_beam_size or 1))
        self._buffer = bytearray()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_active = False
        self._speech_t0: float | None = None
        self._first_partial_mono: float | None = None
        self._last_metrics: dict[str, int] = {}
        self._last_final_meta: dict[str, int | float | str] = {}
        self._partial_task: asyncio.Task[tuple[str, dict[str, Any]]] | None = None
        self._partial_sequence = 0
        self._language_history: list[str] = []
        self._last_language: str = "unknown"
        self._language_changed = False
        self._code_switching_detected = False

    def reset(self) -> None:
        self._buffer.clear()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_active = False
        self._speech_t0 = None
        self._first_partial_mono = None
        self._last_final_meta = {}
        self._partial_sequence = 0
        if self._partial_task and not self._partial_task.done():
            self._partial_task.cancel()
        self._partial_task = None

    def consume_metrics(self) -> dict[str, Any]:
        metrics = {**self._last_metrics, **self._last_final_meta}
        self._last_metrics = {}
        self._last_final_meta = {}
        self._partial_sequence = 0
        self._language_history = []
        self._last_language = "unknown"
        self._language_changed = False
        self._code_switching_detected = False
        return metrics

    async def on_speech_start(self) -> None:
        if self._partial_task and not self._partial_task.done():
            self._partial_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._partial_task
        self._partial_task = None
        self._speech_active = True
        self._buffer.clear()
        self._last_partial_text = ""
        self._last_partial_at = 0.0
        self._speech_t0 = time.monotonic()
        self._first_partial_mono = None
        self._last_metrics = {}
        self._last_final_meta = {}
        self._language_history = []
        self._last_language = "unknown"
        self._language_changed = False
        self._code_switching_detected = False

    async def feed_audio(self, pcm: bytes) -> STTPartial | None:
        """Buffer PCM during an active utterance only.

        Partial inference is throttled and runs in the background. That keeps
        the WebSocket receive loop hot while still surfacing transcript updates.
        """
        if not pcm or not self._speech_active:
            return None
        self._buffer.extend(pcm)
        now = time.monotonic()
        if self._partial_task and self._partial_task.done():
            try:
                partial, meta = self._partial_task.result()
                partial = partial.strip()
            except Exception:
                partial = ""
                meta = {}
            self._partial_task = None
            if partial and partial != self._last_partial_text:
                previous = self._last_partial_text
                self._last_partial_text = partial
                self._record_language(meta)
                if self._first_partial_mono is None:
                    self._first_partial_mono = now
                    if self._speech_t0 is not None:
                        self._last_metrics["stt_partial_ms"] = int(
                            (now - self._speech_t0) * 1000
                        )
                common_prefix = 0
                for left, right in zip(previous, partial, strict=False):
                    if left != right:
                        break
                    common_prefix += 1
                stability = common_prefix / max(1, len(partial)) if previous else 0.0
                self._partial_sequence += 1
                return STTPartial(
                    text=partial,
                    confidence=self._confidence(meta),
                    language=self._language(meta),
                    language_confidence=self._language_confidence(meta),
                    languages=self._language_snapshot(meta),
                    language_changed=self._language_changed,
                    code_switching_detected=self._code_switching_detected,
                    sequence=self._partial_sequence,
                    audio_ms=self._audio_ms(),
                    stability=round(stability, 3),
                )
        enough_audio = len(self._buffer) >= int(self.SAMPLE_RATE * 2 * 0.55)
        interval_ms = self._adaptive_partial_interval_ms()
        elapsed_ms = (
            int((now - self._last_partial_at) * 1000)
            if self._last_partial_at
            else interval_ms
        )
        if enough_audio and self._partial_task is None and elapsed_ms >= interval_ms:
            self._last_partial_at = now
            self._partial_task = asyncio.create_task(
                self._transcribe_with_meta(beam_size=1)
            )
        return None

    async def on_speech_end(self) -> STTFinal:
        self._speech_active = False
        if self._partial_task and not self._partial_task.done():
            self._partial_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._partial_task
            self._partial_task = None
        if self._speech_t0 is not None and self._first_partial_mono is not None:
            self._last_metrics["stt_partial_ms"] = int(
                (self._first_partial_mono - self._speech_t0) * 1000
            )
        if not self._buffer:
            self.reset()
            return STTFinal(text="")
        audio_ms = self._audio_ms()
        text, meta = await self._transcribe_with_meta(beam_size=self._final_beam_size)
        meta = meta or {
            "stt_confidence": 1.0 if text else 0.0,
            "stt_no_speech_probability": 0.0 if text else 1.0,
        }
        self._record_language(meta)
        languages = self._language_snapshot(meta)
        language_changed = self._language_changed
        code_switching_detected = self._code_switching_detected
        sequence = self._partial_sequence
        self.reset()
        self._last_final_meta = {
            **meta,
            "stt_languages": languages,
            "stt_language_changed": language_changed,
            "stt_code_switching_detected": code_switching_detected,
            "stt_sequence": sequence,
        }
        return STTFinal(
            text=text,
            confidence=self._confidence(meta) or 0.0,
            language=self._language(meta),
            language_confidence=self._language_confidence(meta),
            languages=languages,
            language_changed=language_changed,
            code_switching_detected=code_switching_detected,
            sequence=sequence,
            no_speech_probability=self._probability(
                meta.get("stt_no_speech_probability")
            ),
            audio_ms=audio_ms,
        )

    async def _transcribe(self, *, beam_size: int) -> str:
        text, meta = await self._transcribe_with_meta(beam_size=beam_size)
        self._last_final_meta = meta
        return text

    async def _transcribe_with_meta(
        self, *, beam_size: int
    ) -> tuple[str, dict[str, int | float | str]]:
        pcm = bytes(self._buffer)
        if len(pcm) < 320:  # ~10 ms at 16 kHz
            return "", {
                "stt_confidence": 0.0,
                "stt_no_speech_probability": 1.0,
                "stt_language": "unknown",
                "stt_language_confidence": 0.0,
            }

        return await asyncio.to_thread(self._transcribe_sync_locked, pcm, beam_size)

    def _transcribe_sync_locked(
        self, pcm: bytes, beam_size: int
    ) -> tuple[str, dict[str, Any]]:
        with _inference_lock:
            return self._transcribe_sync(pcm, beam_size)

    def _transcribe_sync(
        self, pcm: bytes, beam_size: int
    ) -> tuple[str, dict[str, Any]]:
        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        model = _get_model()
        try:
            segments, info = model.transcribe(
                audio,
                language=None,
                beam_size=beam_size,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=(
                    "Transcribe the user's speech accurately in its detected language. "
                    "Preserve code-switching, names, dates, times, reminders, meetings, "
                    "tasks, and corrections without forcing English."
                ),
            )
            rows = list(segments)
            text = " ".join(s.text.strip() for s in rows if s.text.strip()).strip()
            provider_language = self._normalize_language(
                str(getattr(info, "language", "unknown") or "unknown")
            )
            provider_language_confidence = round(
                float(getattr(info, "language_probability", 0.0) or 0.0), 3
            )
            language, language_confidence, languages, code_switching = (
                self._refine_language_metadata(
                    text,
                    provider_language,
                    provider_language_confidence,
                )
            )
            if not rows:
                return text, {
                    "stt_confidence": 0.0,
                    "stt_no_speech_probability": 1.0,
                    "stt_language": language,
                    "stt_language_confidence": language_confidence,
                    "stt_languages": list(languages) or [language],
                    "stt_code_switching_detected": code_switching,
                }
            avg_logprob = sum(
                float(getattr(s, "avg_logprob", -1.2) or -1.2) for s in rows
            ) / len(rows)
            no_speech_probability = max(
                float(getattr(s, "no_speech_prob", 0.0) or 0.0) for s in rows
            )
            confidence = max(0.0, min(1.0, math.exp(avg_logprob)))
            return text, {
                "stt_confidence": round(confidence, 3),
                "stt_no_speech_probability": round(no_speech_probability, 3),
                "stt_avg_logprob": round(avg_logprob, 3),
                "stt_language": language,
                "stt_language_confidence": language_confidence,
                "stt_languages": list(languages) or [language],
                "stt_code_switching_detected": code_switching,
            }
        except Exception as e:
            log.warning("Whisper streaming transcribe failed: %s", e)
            return "", {
                "stt_confidence": 0.0,
                "stt_no_speech_probability": 1.0,
                "stt_language": "unknown",
                "stt_language_confidence": 0.0,
                "stt_languages": ["unknown"],
                "stt_code_switching_detected": False,
            }

    def _adaptive_partial_interval_ms(self) -> int:
        """Transcribe eagerly at first, then back off as the utterance grows."""
        audio_ms = self._audio_ms()
        if audio_ms < 2_000:
            return self._partial_interval_min_ms
        if audio_ms < 6_000:
            return self._partial_interval_ms
        return self._partial_interval_max_ms

    def _audio_ms(self) -> int:
        return len(self._buffer) * 1000 // (self.SAMPLE_RATE * 2)

    @staticmethod
    def _probability(value: Any) -> float | None:
        if value is None:
            return None
        return max(0.0, min(1.0, float(value)))

    @classmethod
    def _confidence(cls, meta: dict[str, Any]) -> float | None:
        return cls._probability(meta.get("stt_confidence"))

    @staticmethod
    def _language(meta: dict[str, Any]) -> str | None:
        value = str(meta.get("stt_language") or "").strip()
        return value if value else "unknown"

    @classmethod
    def _language_confidence(cls, meta: dict[str, Any]) -> float:
        return cls._probability(meta.get("stt_language_confidence")) or 0.0

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        value = str(language or "").strip().casefold().replace("_", "-")
        if not value:
            return "unknown"
        primary = value.split("-", 1)[0]
        return primary if primary else "unknown"

    @classmethod
    def _language_entries(cls, meta: dict[str, Any]) -> tuple[str, ...]:
        raw_languages = meta.get("stt_languages") or []
        entries = [
            cls._normalize_language(language)
            for language in raw_languages
            if cls._normalize_language(language) != "unknown"
        ]
        if entries:
            return tuple(dict.fromkeys(entries))
        language = cls._language(meta) or "unknown"
        return (language,)

    @classmethod
    def _language_hint_scores(cls, text: str) -> dict[str, int]:
        folded = re.sub(r"\s+", " ", (text or "").casefold()).strip()
        scores: dict[str, int] = {}
        for language, hints in _LANGUAGE_HINTS.items():
            scores[language] = sum(
                1
                for hint in hints
                if re.search(rf"(?<!\w){re.escape(hint)}(?!\w)", folded)
            )
        return scores

    @classmethod
    def _refine_language_metadata(
        cls,
        text: str,
        provider_language: str,
        provider_language_confidence: float,
    ) -> tuple[str, float, tuple[str, ...], bool]:
        scores = cls._language_hint_scores(text)
        best_hint_language = max(scores, key=scores.get, default="unknown")
        best_hint_score = scores.get(best_hint_language, 0)
        if best_hint_score == 0:
            return provider_language, provider_language_confidence, (provider_language,), False

        secondary = max(
            (language for language in scores if language != best_hint_language),
            key=lambda language: scores[language],
            default="unknown",
        )
        secondary_score = scores.get(secondary, 0)
        if provider_language in {best_hint_language, "unknown"}:
            language = best_hint_language
            confidence = min(0.99, max(provider_language_confidence, 0.55 + 0.08 * best_hint_score))
            languages = (language,) if secondary_score == 0 else tuple(
                dict.fromkeys((language, secondary))
            )
            return language, round(confidence, 3), languages, secondary_score > 0

        if provider_language_confidence >= 0.8 and provider_language != best_hint_language:
            confidence = max(0.45, provider_language_confidence - 0.08)
            return (
                provider_language,
                round(confidence, 3),
                tuple(dict.fromkeys((provider_language, best_hint_language))),
                True,
            )
        confidence = min(0.99, 0.58 + 0.06 * best_hint_score)
        return (
            best_hint_language,
            round(confidence, 3),
            tuple(dict.fromkeys((best_hint_language, provider_language))),
            True,
        )

    def _record_language(self, meta: dict[str, Any]) -> None:
        languages = self._language_entries(meta)
        if not languages or languages == ("unknown",):
            self._last_language = "unknown"
            return
        for language in languages:
            if not self._language_history:
                self._language_history.append(language)
            elif self._language_history[-1] != language:
                self._language_changed = True
                self._language_history.append(language)
        if len({entry for entry in self._language_history if entry != "unknown"}) > 1:
            self._code_switching_detected = True
        self._last_language = languages[-1]

    def _language_snapshot(self, meta: dict[str, Any] | None = None) -> list[str]:
        snapshot = [language for language in self._language_history if language != "unknown"]
        if not snapshot and meta is not None:
            entries = self._language_entries(meta)
            if entries and entries != ("unknown",):
                snapshot = list(entries)
            else:
                snapshot = ["unknown"]
        return snapshot
