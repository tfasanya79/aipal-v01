# Neural VAD and contextual acoustic turns

Status: `IN_PROGRESS` (Workstream 4 checks pass; complete API regression gate is not clean).

The active live path accepts PCM16 mono at 16 kHz in 40 ms frames, validates
format and ordering, and sends each accepted frame through a per-session Silero
VAD window. Neural probability directly controls speech start, continuation,
contextual pause, speech end, and barge-in. The server owns the canonical turn
boundary; a client amplitude callback does not finalize a turn.

```text
microphone PCM
-> format/order validation
-> per-session Silero v6 probability
-> acoustic state + pre-roll
-> partial STT and semantic endpoint decision
-> contextual pause interpretation
-> speech end / final STT
-> unified orchestrator
```

## Model, lifecycle, and fallback

The model is Silero VAD v6 bundled as ONNX by Faster-Whisper, running on CPU at
16 kHz. Startup performs a known-frame inference. Each WebSocket session owns a
detector; cancellation and endpoint reset its rolling samples and turn state.
The handshake and voice-capabilities endpoint expose safe model, version,
source, device, thresholds, timing, health, and fallback fields.

Adaptive RMS energy is an explicit development-only fallback. Production with
`fail_closed` refuses startup when Silero cannot initialize or fallback is
active. Empty PCM, malformed samples, oversized frames, stale timestamps,
duplicate/out-of-order sequences, inactive turns, and maximum duration have
deterministic outcomes.

## Canonical acoustic contract

Emitted start, resume, pause, endpoint, and forced-end events carry an optional
`acoustic` object containing state, confidence, reason, speech probability,
silence and utterance durations, playback state, and provider. Its vocabulary is
`silence`, `possible_speech`, `speech_started`, `speech_active`,
`temporary_pause`, `thinking_pause`, `speech_ended`, `barge_in`,
`probable_echo`, `probable_noise`, `forced_endpoint`, and `uncertain`.

Consecutive neural speech is required to start. During AI playback, a higher
threshold plus consecutive frames suppresses moderate playback leakage;
qualified speech becomes `barge_in`. This bounded heuristic is not a claim of
full acoustic echo cancellation.

## Contextual pauses and safeguards

Low neural probability after speech begins starts a pause. At 320 ms the turn
emits `thinking_pause` while remaining open. Semantic completion, transcript
stability, correction/list evidence, language, active intent, pending action,
missing slots, and maximum duration determine the bounded wait. Resumed speech
continues the same turn. Maximum duration emits `forced_endpoint`.

Neural confidence is not gated by RMS, preserving quiet-speech sensitivity.
Idle probability updates the adaptive noise baseline; active speech does not.
Mobile requests OS echo cancellation and noise suppression, but activation is
device/platform dependent.

## Test boundary

The corpus contains 120 reproducible synthetic probability/transport scenarios
covering clean/quiet speech, office/traffic/fan noise, transients, hesitation,
thinking pauses, correction, lists, incomplete requests, short commands,
barge-in, probable echo, packet gaps, missing frames, low gain, and route-change
conditions. Focused tests also run the actual local Silero model and live
WebSocket integration. These are not physical-device tests.

Physical microphone testing, speaker echo, Bluetooth and route switching,
multiple speakers, packet-loss audio quality, broader noise profiles, staging
latency, and production concurrency remain release requirements. No
`VERIFIED_ON_DEVICE` or `PRODUCTION_READY` claim is made.
