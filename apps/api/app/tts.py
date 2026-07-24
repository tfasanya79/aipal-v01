"""Text-to-speech: edge-tts with espeak-ng fallback."""

from __future__ import annotations

import asyncio
import io
import logging
import subprocess
import tempfile
from pathlib import Path

from .config import get_settings

log = logging.getLogger("aipal.tts")

DEFAULT_VOICE = "en-US-JennyNeural"

VOICE_PROFILES = {
    "calm_female": {
        "edge": "en-US-JennyNeural",
        "say": None,
        "espeak": "en",
        "name": "Calm Female",
        "style": "Warm, calm, and steady",
        "pitch": "+0Hz",
        "rate": "-4%",
        "volume": "+0%",
        "pause_ms": 520,
        "warmth": 8,
        "response_pacing": "balanced",
    },
    "calm_male": {
        "edge": "en-US-GuyNeural",
        "say": "Alex",
        "espeak": "en+m3",
        "name": "Calm Male",
        "style": "Relaxed, grounded, and patient",
        "pitch": "-2Hz",
        "rate": "-5%",
        "volume": "+0%",
        "pause_ms": 560,
        "warmth": 7,
        "response_pacing": "slow",
    },
    "coach": {
        "edge": "en-US-DavisNeural",
        "say": "Daniel",
        "espeak": "en-gb+m2",
        "name": "Coach",
        "style": "Direct, focused, and strategic",
        "pitch": "+0Hz",
        "rate": "+2%",
        "volume": "+0%",
        "pause_ms": 360,
        "warmth": 6,
        "response_pacing": "crisp",
    },
    "friendly": {
        "edge": "en-US-JennyNeural",
        "say": "Samantha",
        "espeak": "en+f3",
        "name": "Friendly",
        "style": "Warm and friendly",
        "pitch": "+1Hz",
        "rate": "+0%",
        "volume": "+0%",
        "pause_ms": 440,
        "warmth": 9,
        "response_pacing": "balanced",
    },
    "professional": {
        "edge": "en-US-DavisNeural",
        "say": "Daniel",
        "espeak": "en-gb",
        "name": "Professional",
        "style": "Clear, concise, and composed",
        "pitch": "+0Hz",
        "rate": "+0%",
        "volume": "+0%",
        "pause_ms": 380,
        "warmth": 5,
        "response_pacing": "structured",
    },
    "builder": {
        "edge": "en-US-GuyNeural",
        "say": "Alex",
        "espeak": "en-us+m2",
        "name": "Builder",
        "style": "Startup-focused and execution-minded",
        "pitch": "+0Hz",
        "rate": "+4%",
        "volume": "+0%",
        "pause_ms": 320,
        "warmth": 6,
        "response_pacing": "energetic",
    },
    "energetic": {
        "edge": "en-US-AriaNeural",
        "say": "Victoria",
        "espeak": "en+f5",
        "name": "Energetic",
        "style": "Bright, upbeat, and conversational",
        "pitch": "+2Hz",
        "rate": "+6%",
        "volume": "+2%",
        "pause_ms": 260,
        "warmth": 8,
        "response_pacing": "quick",
    },
    "gentle": {
        "edge": "en-IE-EmilyNeural",
        "say": "Moira",
        "espeak": "en-uk-north+f3",
        "name": "Gentle",
        "style": "Soft, reflective, and reassuring",
        "pitch": "+0Hz",
        "rate": "-8%",
        "volume": "-2%",
        "pause_ms": 650,
        "warmth": 9,
        "response_pacing": "slow",
    },
    "default": {
        "edge": "en-US-AriaNeural",
        "say": "Victoria",
        "espeak": "en+f4",
        "name": "Default",
        "style": "Balanced and clear",
        "pitch": "+0Hz",
        "rate": "+0%",
        "volume": "+0%",
        "pause_ms": 420,
        "warmth": 7,
        "response_pacing": "balanced",
    },
}

VOICE_ALIASES = {
    **VOICE_PROFILES,
    "jenny": VOICE_PROFILES["friendly"],
    "aria": VOICE_PROFILES["default"],
    "guy": VOICE_PROFILES["calm_male"],
    "davis": VOICE_PROFILES["coach"],
    "samantha": VOICE_PROFILES["friendly"],
    "alex": VOICE_PROFILES["calm_male"],
    "victoria": VOICE_PROFILES["energetic"],
    "daniel": VOICE_PROFILES["professional"],
    "moira": VOICE_PROFILES["gentle"],
    "karen": VOICE_PROFILES["energetic"],
}


def voice_options(provider: str | None = None) -> list[dict[str, object]]:
    """Return stable voice IDs the client can save and preview."""
    active_provider = (provider or get_settings().tts_provider or "edge").lower()
    engine = "edge" if active_provider not in {"local", "espeak", "say"} else "local"
    return [
        {
            "id": key,
            "profile_id": key,
            "name": str(meta["name"]),
            "display_name": str(meta["name"]),
            "style": str(meta["style"]),
            "tone": str(meta["style"]),
            "provider": engine,
            "provider_voice_id": str(meta.get("edge") if engine == "edge" else meta.get("say") or meta.get("espeak")),
            "fallback_voice_id": str(meta.get("say") or meta.get("espeak") or "default"),
            "gender_style": "neutral",
            "pitch": str(meta["pitch"]),
            "rate": str(meta["rate"]),
            "volume": str(meta["volume"]),
            "pause_ms": int(meta["pause_ms"]),
            "warmth": int(meta["warmth"]),
            "response_pacing": str(meta["response_pacing"]),
            "sample_preview_label": f"Preview {meta['name']}",
            "preview_text": f"This is the {meta['name']} voice preview.",
            "is_distinct_voice_supported": engine == "edge" or active_provider == "say",
            "fallback_note": "" if engine == "edge" else "Local fallback voices depend on what is installed on this device.",
        }
        for key, meta in VOICE_PROFILES.items()
    ]


def _voice_choice(voice: str | None, provider: str) -> str | None:
    raw = (voice or "default").strip()
    key = raw.lower()
    if key in VOICE_ALIASES:
        return VOICE_ALIASES[key].get(provider)
    return raw or None


async def _edge_synth(text: str, provider_voice: str, profile_id: str) -> bytes:
    import edge_tts

    profile = VOICE_ALIASES.get((profile_id or "calm_female").strip().lower(), VOICE_PROFILES["calm_female"])
    out = io.BytesIO()
    communicate = edge_tts.Communicate(
        text,
        provider_voice,
        rate=str(profile.get("rate") or "+0%"),
        pitch=str(profile.get("pitch") or "+0Hz"),
        volume=str(profile.get("volume") or "+0%"),
    )
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio":
            data = chunk.get("data")
            if data:
                out.write(data)
    return out.getvalue()


def _espeak_synth(text: str, voice: str | None = None) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name
    try:
        espeak_voice = _voice_choice(voice, "espeak") or "en"
        subprocess.run(
            ["espeak-ng", "-v", espeak_voice, "-s", "170", "-w", out_path, text],
            check=True,
            capture_output=True,
        )
        return Path(out_path).read_bytes()
    finally:
        Path(out_path).unlink(missing_ok=True)


def _macos_say_synth(text: str, voice: str | None = None) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as raw:
        raw_path = raw.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav:
        wav_path = wav.name
    try:
        command = ["say"]
        if voice:
            command.extend(["-v", voice])
        command.extend(["-o", raw_path, text])
        subprocess.run(command, check=True, capture_output=True)
        try:
            subprocess.run(
                ["afconvert", raw_path, "-f", "WAVE", "-d", "LEI16@22050", wav_path],
                check=True,
                capture_output=True,
            )
            wav_bytes = Path(wav_path).read_bytes()
            if len(wav_bytes) > 512:
                return wav_bytes
        except Exception:
            pass
        raw_bytes = Path(raw_path).read_bytes()
        return raw_bytes if len(raw_bytes) > 512 else b""
    finally:
        Path(raw_path).unlink(missing_ok=True)
        Path(wav_path).unlink(missing_ok=True)


async def _local_synth(text: str, timeout: float, voice: str | None = None) -> tuple[bytes, str]:
    if (voice or "default").strip().lower() != "default":
        try:
            audio = await asyncio.wait_for(
                asyncio.to_thread(_macos_say_synth, text, _voice_choice(voice, "say")),
                timeout=timeout,
            )
            return audio, "audio/wav"
        except (asyncio.TimeoutError, OSError, subprocess.CalledProcessError) as e:
            log.info("macOS say voice unavailable or timed out: %s; trying espeak-ng voice", e)
    try:
        audio = await asyncio.wait_for(
            asyncio.to_thread(_espeak_synth, text, voice),
            timeout=timeout,
        )
        return audio, "audio/wav"
    except (asyncio.TimeoutError, OSError, subprocess.CalledProcessError) as e:
        log.info("espeak-ng unavailable or timed out: %s; trying macOS say", e)
    if (voice or "default").strip().lower() == "default":
        try:
            audio = await asyncio.wait_for(
                asyncio.to_thread(_macos_say_synth, text, None),
                timeout=timeout,
            )
            return audio, "audio/wav"
        except (asyncio.TimeoutError, OSError, subprocess.CalledProcessError) as e:
            log.warning("macOS say unavailable or timed out: %s", e)
    return b"", "audio/wav"


async def synthesize(text: str, voice: str | None = None) -> tuple[bytes, str]:
    text = (text or "").strip()
    if not text:
        return b"", "audio/mpeg"
    settings = get_settings()
    profile_id = voice or "calm_female"
    chosen = _voice_choice(profile_id, "edge") or DEFAULT_VOICE
    if settings.tts_provider.lower() in {"local", "espeak", "say"}:
        audio, mime = await _local_synth(text, settings.tts_timeout_seconds, voice)
        if audio:
            return audio, mime
        log.warning("local TTS unavailable; trying edge-tts")
    try:
        audio = await asyncio.wait_for(
            _edge_synth(text, chosen, profile_id),
            timeout=settings.tts_timeout_seconds,
        )
        if audio:
            return audio, "audio/mpeg"
    except (asyncio.TimeoutError, Exception) as e:
        log.warning("edge-tts failed: %s; trying espeak-ng", e)
    try:
        audio, mime = await _local_synth(text, settings.tts_timeout_seconds, voice)
        if audio:
            return audio, mime
    except Exception as e:
        log.error("local TTS failed: %s", e)
        return b"", "audio/mpeg"
    return b"", "audio/mpeg"


async def synthesize_stream(text: str, voice: str | None = None):
    """Yield one complete decodable audio clip per sentence (WS splits sentences upstream)."""
    audio, mime = await synthesize(text, voice=voice)
    if audio:
        yield audio, mime
