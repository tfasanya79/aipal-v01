# AiPal Known Limitations Remediation

This is the release evidence record for the known-limitations elimination
program. Workstreams are executed sequentially. A later workstream remains
`NOT_STARTED` until the preceding workstream reaches its required verification
level and receives `WORKSTREAM APPROVED — proceed`.

## Limitation-to-workstream traceability

| ID | Limitation | Severity | Owner component | Workstream | Current status |
| --- | --- | --- | --- | --- | --- |
| KL-01 | Lightweight transcript completion | S1 | Turn detection | 1 | VERIFIED_IN_TEST |
| KL-02 | English-biased endpointing | S1 | Turn detection | 2 | VERIFIED_IN_TEST |
| KL-03 | Lexical topic-change metadata | S2 | Conversation state/orchestrator | 3 | VERIFIED_IN_TEST |
| KL-04 | Neural VAD production fixture coverage | S1 | Voice ingress/VAD | 4 | IN_PROGRESS |
| KL-05 | Base64 PCM transport and preroll efficiency | S1 | Voice transport | 5 | NOT_STARTED |
| KL-06 | Snapshot Faster-Whisper partial decoding | S1 | Streaming STT | 6 | NOT_STARTED |
| KL-07 | Platform-dependent echo/noise handling | S1 | Mobile/browser capture | 7 | NOT_STARTED |
| KL-08 | Missing reconnect/session-resume state machine | S1 | Live session transport | 8 | NOT_STARTED |
| KL-09 | Browser legacy voice fallback | S2 | Browser voice adapter | 9 | NOT_STARTED |
| KL-10 | Deterministic conversation summary | S2 | Summarization/state | 10 | NOT_STARTED |
| KL-11 | Weak topic/goal/intent state intelligence | S1 | Structured reasoning/state | 11 | NOT_STARTED |
| KL-12 | Worker-local ephemeral state without Redis | S1 | Distributed state | 12 | NOT_STARTED |
| KL-13 | Production PostgreSQL drift/migration safety | S1 | Persistence/migrations | 13 | NOT_STARTED |
| KL-14 | External STT/TTS providers not staged | S1 | Provider adapters | 14 | NOT_STARTED |
| KL-15 | Dormant hardcoded conversation intelligence | S1 | Legacy conversation services | 15 | NOT_STARTED |
| KL-16 | Final-response token streaming gaps | S1 | LLM/response stream | 16 | NOT_STARTED |
| KL-17 | Incremental TTS edge cases and playback proof | S1 | TTS/playback | 17 | NOT_STARTED |
| KL-18 | Transitional legacy internals behind ports | S2 | Dependency injection | 18 | NOT_STARTED |
| KL-19 | Missing transactional event outbox | S1 | Persistence/events | 19 | NOT_STARTED |
| KL-20 | Incomplete speech-start context consumption | S2 | Memory/context retrieval | 20 | NOT_STARTED |
| KL-21 | Weak production configuration enforcement | S1 | Configuration/readiness | 21 | NOT_STARTED |
| KL-22 | CPU-only production LLM latency | S1 | LLM provider/deployment | 22 | NOT_STARTED |
| KL-23 | Missing staging and physical-device release gate | S1 | Release engineering | 23 | NOT_STARTED |

## KL-01 — Lightweight transcript completion

- Original limitation: the active `TranscriptEndpointModel` was a hand-weighted
  English feature score that directly controlled the silence threshold used by
  the live WebSocket path.
- Severity: S1.
- Owner component: `apps/api/app/services/turn_detection.py`.
- Implementation status: VERIFIED_IN_TEST.
- Active code path:
  `ws_session.live_session -> HybridTurnDetector.update_transcript/process ->
  endpoint_detected -> _finalize_detected_turn -> unified orchestrator`.
- Dormant/legacy alternatives: client `speech_start` and `speech_end` messages
  are rejected by voice protocol 4.0; mobile amplitude is not authoritative.
- Configuration dependencies: STT partial confidence, language, stability,
  server VAD, maximum utterance duration,
  `SEMANTIC_ENDPOINTING_PROVIDER`, `SEMANTIC_ENDPOINTING_MIN_WAIT_MS`, and
  `SEMANTIC_ENDPOINTING_MAX_WAIT_MS`.
- Runtime dependencies: Faster-Whisper STT metadata, Silero VAD, local semantic
  classifier runtime, WebSocket voice protocol 4.0.
- Existing tests: `test_turn_detection_phase4.py` and the server-authoritative
  endpoint cases in `test_ws_live_voice_v2.py`.
- Files changed:
  `apps/api/.env.example`, `apps/api/app/config.py`,
  `apps/api/app/services/embedding_service.py`,
  `apps/api/app/services/turn_detection.py`,
  `apps/api/app/routers/ws_session.py`,
  `apps/api/scripts/preload_embedding_model.py`,
  `apps/api/tests/test_turn_detection_phase4.py`,
  `apps/api/tests/test_ws_live_voice_v2.py`,
  `docs/architecture/conversation-phase-4-turn-detection.md`, and this record.
- Tests added: structured four-way decisions, primary-provider selection,
  explicit fallback disclosure, canonical missing-slot context, thinking pauses,
  corrections, lists, noisy and corrected partials, short commands,
  confirmations, maximum-duration enforcement, acceptance latency metrics, and
  WebSocket handshake/final-event propagation.
- Automated evidence: focused voice and WebSocket suite passed 30/30 tests; the
  complete API suite passed 289 tests with one isolated PostgreSQL/pgvector test
  skipped because `RUN_POSTGRES_PHASE5_TESTS=1` and an external test database
  were not supplied; mobile tests passed 13/13; Flutter analysis reported no
  issues; Ruff passed for all Workstream 1 Python files; compile and whitespace
  validation passed; the deployment preload check passed with
  `endpointing=local_statistical_endpoint_v1`.
- Manual evidence: the ten required utterances were submitted directly to the
  active `TranscriptEndpointModel` from the API virtual environment. Decisions
  matched the expected complete/incomplete behavior; observed waits were
  `[1400, 440, 560, 600, 600, 440, 1400, 240, 240, 1400]` milliseconds.
- Staging evidence: not required for Workstream 1 approval; staging aggregate
  validation belongs to Workstream 23.
- Metrics: median endpoint delay 580 ms; p95 endpoint delay 1,400 ms; false
  cutoff count/rate 0/10 (0%); over-wait count/rate 0/10 (0%); classifier
  median 0.094 ms and p95 0.182 ms on the development validation host.
- Legacy path disposition: the hand-weighted completion probability and
  threshold selector were removed from the active path. A bounded linguistic
  implementation is isolated as an explicitly configured fallback and is
  disclosed in transport metadata.
- Remaining risk: the validation corpus is intentionally English-focused;
  multilingual parity is not claimed and remains KL-02/Workstream 2. Aggregate
  staging and physical-device release evidence remains KL-23.
- Rollback strategy: retain the current detector class boundary and revert the
  semantic classifier implementation/configuration without changing transport,
  STT, orchestration, or persistence contracts.
- Final disposition: VERIFIED_IN_TEST.

## Sequential gate

Workstream 2 is explicitly blocked from implementation until KL-01 is at least
`VERIFIED_IN_TEST` and the Workstream 1 decision is
`WORKSTREAM APPROVED — proceed`.

## KL-02 — English-biased endpointing

- Original limitation: English-only incomplete tails and command phrases were
  primary completion evidence while other languages depended on punctuation,
  confidence, stability, length, and silence.
- Status: VERIFIED_IN_TEST. Workstream 3 remains NOT_STARTED.
- Active flow: PCM -> Silero VAD -> Faster-Whisper partial -> provider language
  metadata/history -> multilingual MiniLM semantic endpointing -> structured
  endpoint decision -> final STT -> unified orchestrator.
- Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, Qdrant
  FastEmbed ONNX export, 384 dimensions, approximately 0.22 GB, CPU,
  deployment download plus startup preload.
- Language handling: provider language/probability are preserved; absent values
  are `unknown`; monotonic sequence guards reject stale partial/language updates;
  code-switch history remains turn-scoped. A small high-specificity Pidgin
  marker detector compensates for provider `en` labeling but never decides
  endpoint completion.
- Tested languages: English/Nigerian English (`en`), Nigerian Pidgin/mixed
  English-Pidgin (`pcm`), and French (`fr`). French was selected for reliable
  coverage in Faster-Whisper and multilingual MiniLM. Untested languages expose
  `language-agnostic fallback active`; parity is not claimed.
- Corpus: 300 generated/degraded transcript scenarios, 100 per language and 20
  categories per language. It includes punctuation loss, substitutions,
  repetitions/revisions, low-confidence names, lists, corrections, hesitation,
  slots, code switching, short commands, and maximum duration.
- Metrics per language: 0% false cutoff, 0% over-wait, 15% deliberately
  uncertain, 440 ms complete-turn median, 700 ms complete-turn p95, and 240 ms
  short-command median. Classifier latency was 3.710 ms median / 4.859 ms p95 on
  the development host. Every category scored 5/5 at the complete-vs-continue
  safety boundary for each language.
- Fallback: exceptions and >20 ms inference return deterministic `uncertain`,
  `semantic_model_failure`/`semantic_model_timeout`, and 900 ms wait. Production
  `fail_closed` readiness rejects unavailable or fallback endpointing. Active
  model/fallback configuration is exposed by the handshake and capabilities
  endpoint without cache paths.
- Legacy disposition: English incomplete tails, English short-command phrases,
  and punctuation checks remain only in the explicit linguistic failure
  fallback or bounded safeguards. The phrase-trained statistical classifier is
  no longer the configured active provider. STT language metadata is consumed
  rather than discarded.
- Verification boundary: automated transcript and synthetic/prerecorded fixture
  evidence only. Physical-device multilingual audio, speaker echo, Bluetooth,
  background-noise breadth, and staging provider latency remain unverified.
- Rollback: set the endpoint provider to the previous local statistical provider
  in non-production while preserving the endpoint/STT/WebSocket contracts;
  production fallback remains fail-closed.

## KL-03 — Lexical topic-change metadata

- Original limitation: endpointing calculated a token-overlap boolean that was
  passive metadata, while canonical state replaced `current_topic` with every
  raw utterance and confirmations were not topic-bound.
- Status: VERIFIED_IN_TEST. Workstream 4 remains NOT_STARTED.
- Implementation: a local multilingual semantic classifier now emits the
  canonical `TopicTransitionDecision` before reasoning. Backend policy applies
  the decision atomically to structured active topic/history state and filters
  context before the unified brain can resolve confirmations or execute tools.
- Safety: pending confirmations bind action, topic, turn, user, and conversation
  IDs plus expiry. Unrelated, cancelled, stale, duplicated, expired, ambiguous,
  timed-out, or invalid transitions cannot execute an old action.
- Behavior: continuation/refinement/modification/correction preserves valid
  topic state; related subtopics create linked topics; unrelated topics pause
  old state and clear unsafe pending context; semantic resume restores only a
  safe paused topic without replaying tools.
- Corpus: 250 multilingual/adversarial scenarios across English, Nigerian
  English, Nigerian Pidgin, English/Pidgin, and French, with the required class
  distribution. Calibrated semantic-feature accuracy was 100% overall and per
  class, with zero unsafe pending preservation, zero duplicate topic creation,
  and 100% stale-confirmation rejection.
- Model: Workstream 2 multilingual MiniLM FastEmbed ONNX model, CPU, bounded
  candidate cache, approximately 5 ms median / 9 ms p95 after preload on the
  development host. Controlled fallback rate was 0%; intentional ambiguous
  scenarios were 4% of the corpus.
- Runtime paths: text, live voice, and uploaded audio all use the same
  `ConversationOrchestrator` topic phase. Handshake/capabilities diagnostics and
  deployment preload expose/validate safe non-secret configuration.
- Verification boundary: automated tests only. Real-user validation, staging
  concurrency, production multi-worker coherence, broader languages, and
  physical-device conversation testing remain required.
- Details: `docs/architecture/conversation-topic-state.md`.

## KL-04 — Neural VAD and contextual pause interpretation

- Original limitation: Silero probability influenced the active path, but it
  lacked a formal lifecycle/readiness contract, production fallback failed open,
  pause meaning was implicit, diagnostics were sparse, and acoustic corpus
  coverage was insufficient.
- Status: IN_PROGRESS. Workstream 5 remains NOT_STARTED. Workstream 4-owned
  checks pass, but the complete API suite exposed intermittent pre-existing
  semantic-classifier timeout failures, so the sequential approval gate is open.
- Active flow: PCM validation -> per-session Silero v6 -> acoustic decision and
  pre-roll -> partial STT -> multilingual semantic endpoint plus canonical
  topic/intent state -> contextual pause/end -> final STT -> orchestrator.
- Model: Silero VAD v6 bundled ONNX through Faster-Whisper, CPU, 16 kHz. Startup
  performs known-frame inference; cancellation/end reset session state.
  Production fail-closed rejects unavailable neural VAD or active energy fallback.
- Contract: additive `acoustic` metadata uses a fixed state vocabulary without
  changing the Workstream 1 endpoint schema. Handshake/capabilities expose safe
  model, threshold, latency, health, and fallback diagnostics.
- Context: semantic completion, transcript stability, correction/list evidence,
  language, intent, pending action, and missing slots select the bounded wait.
- Echo/noise: playback barge-in requires consecutive stronger neural scores;
  moderate leakage is suppressed. This is not production echo-cancellation proof.
- Corpus: 120 synthetic scenarios across 12 behavioral categories and 10
  acoustic/transport conditions, plus actual local Silero inference. No fixture
  is labeled physical-device validation.
- Transport safety: inactive turns, duplicate/out-of-order sequence, stale
  timestamp, malformed/oversized PCM, gaps, cancellation, and maximum duration
  have deterministic outcomes and counters.
- Fallback: adaptive RMS energy is development-only and disclosed; fail-closed
  production never silently substitutes it.
- Verification boundary: physical microphones, speaker echo, Bluetooth/route
  switching, multiple speakers, packet-loss quality, broader background noise,
  staging latency, and production concurrency remain required.
- Details: `docs/architecture/conversation-neural-vad.md`.
