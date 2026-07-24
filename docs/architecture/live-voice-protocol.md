# Live Voice v2 — WebSocket protocol

Full-duplex voice over `GET /api/v2/ws/session?token=<JWT>`.

See [ADR live-voice-v2](../decisions/live-voice-v2.md) for rationale and STT provider selection.

## Connection lifecycle

1. Client connects with JWT query param.
2. Server sends `session_started` with `session_id`.
3. Client streams PCM + VAD events; server streams transcripts, LLM deltas, TTS chunks.
4. Client sends `end` or disconnects → server sends `session_ended`.

## State machine (server → client `state` messages)

| State | Meaning |
|-------|---------|
| `listening` | Ready for user speech |
| `thinking` | STT final received; LLM streaming |
| `speaking` | TTS chunks being sent |

Mic stays hot on the client during `speaking` (full-duplex). Client VAD may trigger `interrupt` on barge-in.

---

## Client → server

All messages are JSON text frames.

### `audio_frame`

Stream 16 kHz mono PCM (16-bit LE). Payload is base64-encoded bytes.

```json
{"type": "audio_frame", "data": "<base64 PCM>"}
```

Sent continuously while Live is active, including during TTS playback.

### `speech_start`

User started speaking (client VAD).

```json
{"type": "speech_start", "turn_id": "uuid"}
```

### `speech_end`

User stopped speaking; triggers final STT + brain pipeline.

```json
{"type": "speech_end", "turn_id": "uuid"}
```

### `interrupt`

Cancel in-flight turn (LLM + TTS). Client should flush playback queue.

```json
{"type": "interrupt", "turn_id": "uuid"}
```

### `text_turn`

Text-only turn on the same streaming path (parity with voice).

```json
{"type": "text_turn", "text": "remind me to swim at 6", "turn_id": "uuid"}
```

### `ping` / `end`

```json
{"type": "ping"}
{"type": "end"}
```

---

## Server → client

### `session_started`

```json
{"type": "session_started", "session_id": "uuid", "state": "live"}
```

### `transcript_partial`

Streaming STT while user speaks.

```json
{"type": "transcript_partial", "turn_id": "uuid", "text": "remind me to"}
```

### `transcript_final`

Final transcript after `speech_end`.

```json
{"type": "transcript_final", "turn_id": "uuid", "text": "remind me to swim at six"}
```

### `state`

```json
{"type": "state", "state": "thinking"}
```

Values: `listening`, `thinking`, `speaking`.

### `reply_delta`

Streaming LLM token chunk (plain text only; plan JSON block stripped from deltas).

```json
{"type": "reply_delta", "turn_id": "uuid", "text": "Sure, "}
```

### `audio_chunk`

Sentence-level TTS output.

```json
{
  "type": "audio_chunk",
  "turn_id": "uuid",
  "data": "<base64 audio>",
  "mime": "audio/mpeg",
  "index": 0
}
```

### `turn_complete`

Turn finished successfully.

```json
{
  "type": "turn_complete",
  "turn_id": "uuid",
  "reply": "full reply text",
  "tool_actions": [],
  "plan_draft": null,
  "draft_confirmed": false,
  "metrics": {
    "stt_final_ms": 420,
    "llm_first_token_ms": 180,
    "tts_first_chunk_ms": 95,
    "turn_total_ms": 2100
  }
}
```

### `turn_cancelled`

After `interrupt` or task cancellation.

```json
{"type": "turn_cancelled", "turn_id": "uuid"}
```

### `error`

```json
{"type": "error", "message": "description", "turn_id": "uuid"}
```

### `pong` / `session_ended`

```json
{"type": "pong"}
{"type": "session_ended", "state": "resting"}
```

---

## STT provider selection

| Environment | Default | Upgrade trigger |
|-------------|---------|-----------------|
| Dev / staging | `whisper_stream` (self-hosted) | N/A |
| Production (small team) | `whisper_stream` | p95 STT > 1.5 s or > 2 concurrent Live sessions |
| Production (public) | Evaluate managed API | See ADR managed STT table |

Protocol is provider-agnostic: swapping STT backend does not change client messages.

---

## Legacy

- `audio_chunk` (client → server) from v1 stub is replaced by `audio_frame`.
- `POST /turn/audio` remains for one release with `LIVE_VOICE_V2=0`; not used by v2 mobile client.
