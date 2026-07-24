# ADR: Live Voice v2 — full-duplex WebSocket

**Status:** Accepted  
**Date:** 2026-06-16

## Context

Live Voice v1 used batch REST (`POST /turn/audio`): upload a recorded segment, wait for full STT → LLM → TTS, then play. This turn-taking model blocks the mic during playback, adds round-trip latency, and cannot interrupt server-side work cleanly.

## Decision

Replace the REST Live audio path with **full-duplex WebSocket Live Voice v2**:

| Layer | v1 (deprecated) | v2 |
|-------|-----------------|-----|
| Transport | HTTP multipart upload | Duplex `/ws/session` |
| STT | Batch faster-whisper on file | Self-hosted streaming Whisper on VM |
| LLM | 1–2 non-streaming calls | One streaming DeepSeek call |
| TTS | Full MP3 in JSON | Sentence-chunked edge-tts over WS |
| Interrupt | Client stale-response guard | Server `interrupt` + client queue flush |
| Session | WS id + REST mismatch risk | Single WS `session_id` for all Live turns |

### Full-duplex semantics

- Client continuously streams 16 kHz mono PCM on the same WebSocket while assistant audio plays.
- Server pipelines STT partials, LLM tokens, and TTS chunks — no batch upload gate.
- `interrupt` cancels in-flight LLM + TTS server-side; client flushes its playback queue.
- VAD remains **client-side** (`speech_start` / `speech_end`). During `speaking`, the server may apply lightweight energy checks to ignore echo; Android AEC quality varies by device — document in QA.

### STT default: self-hosted streaming Whisper

**No new API purchase required.** Default provider is `whisper_stream` (faster-whisper on the VM, CPU `int8`).

Implementation:

1. Buffer PCM from `audio_frame` messages.
2. Emit `transcript_partial` every ~500 ms (configurable) via fast inference (`beam_size=1`, `vad_filter=True`).
3. On `speech_end`, run a higher-accuracy final pass (`beam_size=3–5`) → `transcript_final`.
4. Global `asyncio.Semaphore(1)` — one CPU Whisper job at a time per VM.

Config: `stt_provider=whisper_stream`, `whisper_model=base`, `whisper_device=cpu`, `whisper_compute_type=int8`.

### CPU now, GPU later

When concurrent Live users or p95 STT latency exceed thresholds, upgrade the VM:

| Setting | CPU (default) | GPU path |
|---------|---------------|----------|
| `whisper_device` | `cpu` | `cuda` |
| `whisper_compute_type` | `int8` | `float16` |
| Model | `base` | `small` or `distil-small.en` |

### Managed STT upgrade criteria (public deployment)

Keep the `StreamingSTT` protocol stable so adding `DeepgramStreamingSTT` (or AssemblyAI) is a new class + env key, not a protocol rewrite. **Do not require managed STT to ship v2.**

| Switch to managed STT (e.g. Deepgram, AssemblyAI) when… | Why |
|----------------------------------------------------------|-----|
| **Concurrent Live sessions** exceed ~2–3 on CPU Whisper | CPU inference becomes the bottleneck; partial + final jobs queue |
| **p95 time-to-final-transcript** after `speech_end` exceeds ~1.5 s | Public voice UX degrades before LLM even starts |
| **Public / multi-tenant deployment** | Vendor SLAs, auto-scaling, and ops burden vs. tuning Whisper on one VM |
| **Compliance / privacy policy** | Third-party voice processing must be disclosed; self-hosted keeps audio on your VM |
| **Geographic latency** | Managed edge endpoints can beat single-region VM CPU |

**Dev/staging default:** self-hosted streaming Whisper.  
**Production public scale:** evaluate managed STT per this table.

### Target SLIs (CPU self-hosted)

- Time-to-first-audio: **< 3 s** p50 / **< 5 s** p95 after `speech_end`.
- Log per turn: `stt_partial_ms`, `stt_final_ms`, `llm_first_token_ms`, `tts_first_chunk_ms`, `turn_total_ms`.

### Deprecation

- `POST /turn/audio` is deprecated for Live; retained one release behind `LIVE_VOICE_V2=0` fallback only.
- Web Live may continue REST fallback until PCM streaming is supported in browser.

## Consequences

- Single WebSocket session owns all Live state — no REST/WS session id drift.
- Voice turns use one streaming LLM call with optional plan JSON in a trailing block (no second extraction call).
- Self-hosted STT limits concurrent Live users on CPU; document upgrade path before public launch.
