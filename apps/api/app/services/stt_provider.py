"""Streaming STT provider abstraction."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..config import Settings


class STTPartial(BaseModel):
    """A non-terminal transcript hypothesis for the active utterance."""

    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float | None = Field(default=None, ge=0, le=1)
    language: str = "unknown"
    language_confidence: float = Field(default=0.0, ge=0, le=1)
    languages: list[str] = Field(default_factory=list)
    language_changed: bool = False
    code_switching_detected: bool = False
    sequence: int | None = Field(default=None, ge=0)
    audio_ms: int = Field(default=0, ge=0)
    stability: float | None = Field(default=None, ge=0, le=1)


class STTFinal(BaseModel):
    """Terminal transcription and provider metadata for one utterance."""

    model_config = ConfigDict(extra="forbid")

    text: str
    confidence: float = Field(default=0, ge=0, le=1)
    language: str = "unknown"
    language_confidence: float = Field(default=0.0, ge=0, le=1)
    languages: list[str] = Field(default_factory=list)
    language_changed: bool = False
    code_switching_detected: bool = False
    sequence: int | None = Field(default=None, ge=0)
    no_speech_probability: float | None = Field(default=None, ge=0, le=1)
    audio_ms: int = Field(default=0, ge=0)


@runtime_checkable
class StreamingSTT(Protocol):
    async def feed_audio(self, pcm: bytes) -> STTPartial | None:
        """Feed PCM bytes and return a changed partial hypothesis, if ready."""
        ...

    async def on_speech_start(self) -> None: ...

    async def on_speech_end(self) -> STTFinal:
        """Return the final transcript and provider metadata."""
        ...

    def consume_metrics(self) -> dict[str, Any]:
        """Return per-turn STT timing metrics (e.g. stt_partial_ms)."""
        ...

    def reset(self) -> None: ...


def get_streaming_stt(settings: Settings) -> StreamingSTT:
    provider = (settings.stt_provider or "whisper_stream").lower()
    if provider == "whisper_stream":
        from .whisper_streaming_stt import WhisperStreamingSTT

        return WhisperStreamingSTT(settings)
    raise ValueError(f"Unknown stt_provider: {provider}")
