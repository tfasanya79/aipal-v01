# AiPal Companion Phase 1

This phase adds the first real companion layer on top of the existing task and voice app.

## What changed

- New `POST /api/v2/companion/turn` endpoint
- New companion conversation and message tables
- New user profile, goal, memory, emotional state, and reflection tables
- Lightweight mode routing and emotion detection
- Memory retrieval before the LLM reply
- Memory extraction and persistence after the reply
- Flutter surfaces now receive:
  - `mode`
  - `emotion`
  - `memories_used`
  - `suggested_actions`
  - `requires_confirmation`
  - `confirmation_prompt`

## Request flow

1. User sends text or transcript.
2. Safety check runs first.
3. Conversation context is loaded.
4. User profile, active goals, and similar memories are retrieved.
5. Emotion is detected.
6. Mode is classified.
7. Prompt is assembled.
8. LLM generates the reply.
9. Optional actions and confirmation needs are decided.
10. Message and extracted memories are stored.

## Memory rules

- Important memories are stored with embeddings.
- Sensitive memories are marked and require confirmation.
- Memory retrieval excludes paused or unapproved items.

## Flutter integration

- Companion and Text Chat now read the companion response metadata.
- The UI can show mode, emotion, memory usage, suggested actions, and confirmation prompts.

## Notes

- Legacy task, Today, and live voice routes remain available.
- Old conversation history is still mirrored for compatibility.
- Phase 2 can expand into richer memory controls, goals, reflections, and voice-mode parity.
