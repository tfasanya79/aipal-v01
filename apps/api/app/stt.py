"""Local STT via faster-whisper."""

from __future__ import annotations

import subprocess
import tempfile
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

from .config import get_settings


@lru_cache
def _get_model() -> Any:
    from faster_whisper import WhisperModel

    settings = get_settings()
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def _ffmpeg_to_wav16_mono(path: str) -> str:
    if path.lower().endswith(".wav"):
        return path
    settings = get_settings()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out = f.name
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ff = get_ffmpeg_exe()
        subprocess.run(
            [
                ff,
                "-y",
                "-nostdin",
                "-i",
                path,
                "-t",
                str(max(1, settings.max_audio_decode_seconds)),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-af",
                "aresample=async=1:first_pts=0",
                out,
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        Path(out).unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg conversion failed: {e!s}") from e
    return out


def transcribe_path_with_meta(path: str) -> tuple[str, dict[str, Any]]:
    model = _get_model()
    settings = get_settings()
    converted = _ffmpeg_to_wav16_mono(path) if not path.lower().endswith(".wav") else path
    try:
        def _transcribe(*, vad_filter: bool) -> tuple[str, dict[str, Any]]:
            segments, info = model.transcribe(
                converted,
                language=None,
                beam_size=max(1, settings.whisper_beam_size),
                vad_filter=vad_filter,
                condition_on_previous_text=False,
            )
            rows = list(segments)
            transcript = " ".join(s.text.strip() for s in rows if s.text.strip()).strip()
            meta: dict[str, Any] = {
                "stt_confidence": 0.0 if not rows else round(
                    max(
                        0.0,
                        min(
                            1.0,
                            math.exp(
                                sum(
                                    float(getattr(s, "avg_logprob", -1.2) or -1.2)
                                    for s in rows
                                )
                                / max(1, len(rows))
                            ),
                        ),
                    ),
                    3,
                ),
                "stt_no_speech_probability": 1.0 if not rows else round(
                    max(float(getattr(s, "no_speech_prob", 0.0) or 0.0) for s in rows),
                    3,
                ),
                "stt_language": str(getattr(info, "language", "unknown") or "unknown"),
                "stt_language_confidence": round(
                    float(getattr(info, "language_probability", 0.0) or 0.0), 3
                ),
                "stt_languages": [
                    str(getattr(info, "language", "unknown") or "unknown")
                ],
                "stt_language_changed": False,
                "stt_code_switching_detected": False,
            }
            return transcript, meta

        transcript, meta = _transcribe(vad_filter=True)
        if transcript:
            return transcript, meta
        # Browser recordings can be aggressively noise-suppressed; if VAD
        # removes the whole clip, retry once rather than pretending nothing
        # was said.
        return _transcribe(vad_filter=False)
    finally:
        if converted != path:
            Path(converted).unlink(missing_ok=True)


def transcribe_path(path: str) -> str:
    transcript, _meta = transcribe_path_with_meta(path)
    return transcript
