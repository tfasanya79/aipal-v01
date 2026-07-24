"""Versioned PCM ingress contracts for the live voice WebSocket."""

from __future__ import annotations

from dataclasses import dataclass


VOICE_PROTOCOL_VERSION = "4.0"
PCM_SAMPLE_RATE = 16_000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH_BYTES = 2
MAX_AUDIO_FRAME_BYTES = 64 * 1024


def audio_format_is_supported(payload: dict) -> bool:
    """Validate supplied format fields while allowing older clients to omit them."""
    encoding = payload.get("encoding")
    sample_rate = payload.get("sample_rate")
    channels = payload.get("channels")
    return (
        encoding in {None, "pcm_s16le"}
        and sample_rate in {None, PCM_SAMPLE_RATE}
        and channels in {None, PCM_CHANNELS}
    )


@dataclass(frozen=True, slots=True)
class AudioFrameAcceptance:
    accepted: bool
    duplicate: bool = False
    reason: str | None = None


class VoiceAudioIngress:
    """Per-connection frame ordering, deduplication, and size enforcement."""

    def __init__(self, *, max_utterance_ms: int | None = 30_000) -> None:
        self._max_bytes = (
            PCM_SAMPLE_RATE
            * PCM_CHANNELS
            * PCM_SAMPLE_WIDTH_BYTES
            * max_utterance_ms
            // 1000
            if max_utterance_ms is not None
            else None
        )
        self._turn_id: str | None = None
        self._last_sequence = -1
        self._accepted_bytes = 0
        self._accepted_frames = 0
        self._duplicate_frames = 0
        self._sequence_gaps = 0
        self._last_timestamp_ms: int | None = None
        self._out_of_order_frames = 0

    @property
    def active_turn_id(self) -> str | None:
        return self._turn_id

    def start(self, turn_id: str) -> None:
        self._turn_id = turn_id
        self._last_sequence = -1
        self._accepted_bytes = 0
        self._accepted_frames = 0
        self._duplicate_frames = 0
        self._sequence_gaps = 0
        self._last_timestamp_ms = None
        self._out_of_order_frames = 0

    def accept(
        self,
        *,
        turn_id: str,
        sequence: int | None,
        pcm: bytes,
        timestamp_ms: int | None = None,
    ) -> AudioFrameAcceptance:
        if self._turn_id != turn_id:
            return AudioFrameAcceptance(False, reason="inactive_turn")
        if not pcm:
            return AudioFrameAcceptance(False, reason="empty_frame")
        if len(pcm) > MAX_AUDIO_FRAME_BYTES:
            return AudioFrameAcceptance(False, reason="frame_too_large")
        if timestamp_ms is not None and timestamp_ms < 0:
            return AudioFrameAcceptance(False, reason="invalid_timestamp")
        resolved_sequence = self._last_sequence + 1 if sequence is None else sequence
        if resolved_sequence <= self._last_sequence:
            self._duplicate_frames += 1
            if resolved_sequence < self._last_sequence:
                self._out_of_order_frames += 1
            return AudioFrameAcceptance(
                False,
                duplicate=resolved_sequence == self._last_sequence,
                reason=(
                    "duplicate_sequence"
                    if resolved_sequence == self._last_sequence
                    else "out_of_order_sequence"
                ),
            )
        if (
            timestamp_ms is not None
            and self._last_timestamp_ms is not None
            and timestamp_ms <= self._last_timestamp_ms
        ):
            self._out_of_order_frames += 1
            return AudioFrameAcceptance(False, reason="stale_timestamp")
        if (
            self._max_bytes is not None
            and self._accepted_bytes + len(pcm) > self._max_bytes
        ):
            return AudioFrameAcceptance(False, reason="utterance_too_large")
        if len(pcm) % (PCM_CHANNELS * PCM_SAMPLE_WIDTH_BYTES):
            return AudioFrameAcceptance(False, reason="malformed_pcm_frame")
        if resolved_sequence > self._last_sequence + 1:
            self._sequence_gaps += resolved_sequence - self._last_sequence - 1
        self._last_sequence = resolved_sequence
        if timestamp_ms is not None:
            self._last_timestamp_ms = timestamp_ms
        self._accepted_bytes += len(pcm)
        self._accepted_frames += 1
        return AudioFrameAcceptance(True)

    def finish(self, turn_id: str) -> dict[str, int]:
        if turn_id != self._turn_id:
            return {}
        metrics = {
            "audio_frames": self._accepted_frames,
            "audio_bytes": self._accepted_bytes,
            "audio_ms": self._accepted_bytes
            * 1000
            // (PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_SAMPLE_WIDTH_BYTES),
            "audio_duplicate_frames": self._duplicate_frames,
            "audio_sequence_gaps": self._sequence_gaps,
            "audio_out_of_order_frames": self._out_of_order_frames,
        }
        self._turn_id = None
        return metrics

    def take_metrics(self) -> dict[str, int]:
        """Return interval counters while preserving continuous stream ordering."""
        metrics = {
            "audio_frames": self._accepted_frames,
            "audio_bytes": self._accepted_bytes,
            "audio_ms": self._accepted_bytes
            * 1000
            // (PCM_SAMPLE_RATE * PCM_CHANNELS * PCM_SAMPLE_WIDTH_BYTES),
            "audio_duplicate_frames": self._duplicate_frames,
            "audio_sequence_gaps": self._sequence_gaps,
            "audio_out_of_order_frames": self._out_of_order_frames,
        }
        self._accepted_bytes = 0
        self._accepted_frames = 0
        self._duplicate_frames = 0
        self._sequence_gaps = 0
        self._out_of_order_frames = 0
        return metrics

    def cancel(self) -> None:
        self._turn_id = None
