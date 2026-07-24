# Phase 10 — Conversation Quality and Release Gate

Status: approved and complete. Phases 5–10 are approved as one production
integration baseline, subject to the deployment-provider SLO gate below.

## Decision

Phase 10 introduces no second conversation path and no product capability. It is
the release gate for the single conversation brain delivered by Phases 1–9.
Approval is fail-closed: a failed or skipped required gate blocks release, while
an environment-specific provider gate may be recorded separately only when the
deployment environment enforces the same SLO before traffic is enabled.

The gate owns four things:

1. a deterministic cross-phase regression suite;
2. a PostgreSQL/pgvector integration job using the production database family;
3. bounded concurrency, cancellation, and internal-latency checks;
4. one auditable command and CI workflow that cannot silently omit a category.

## Quality architecture

```text
                           Phase 10 release gate
                                      |
             +------------------------+------------------------+
             |                        |                        |
       static invariants       deterministic runtime      deployment gates
             |                        |                        |
      one brain/prompt/        unit + integration +       PostgreSQL/pgvector
      registry/provider       multi-turn + interruption   provider first-token
      policy boundaries       + mixed-modality load       and first-audio SLOs
             |                        |                        |
             +------------------------+------------------------+
                                      |
                              signed gate manifest
                                      |
                         approve / block / roll back
```

The gate observes the production modules through public ports. Tests may replace
external LLM, embedding, STT, and TTS providers with deterministic fakes, but
must not replace the orchestrator, state manager, memory manager, prompt builder,
reasoning validator, tool registry, or streaming event path being verified.

## Required matrix

| Quality category | Required evidence | Release rule |
| --- | --- | --- |
| Unit | state, retrieval, prompt, reasoning contract, registry, segmentation | zero failures |
| Integration | authenticated REST, WebSocket, database, registry handlers | zero failures |
| Load | concurrent retrieval, tools, streams, and mixed user turns | no leakage; bounded p95 |
| Voice interruption | barge-in and cancellation through provider and TTS cleanup | under 100 ms internal propagation; no partial persistence |
| Memory | stable preload plus query-specific semantic retrieval | bounded candidates; user isolation |
| Planner | draft, durable confirmation, reconnect, exactly-once apply | no mutation before confirmation |
| Calendar | conversational lookup through the registry | authenticated user isolation |
| Tool execution | text, voice, uploaded audio, and explicit UI converge | one immutable registry executor |
| Multi-turn | prior state and recent discussion affect the next turn | one durable state record |
| Continuity | reconnect and modality change retain state and pending action | no stale or duplicated state |
| Security | prompt injection, unknown tools, forged identity/confirmation | fail closed |
| Database | migrations, backfill, vector query, HNSW plan | required PostgreSQL job passes |

## Cross-phase execution flow

```text
authenticated input
  -> ConversationOrchestrator
  -> durable ConversationState
  -> stable + query MemoryManager retrieval
  -> canonical PromptBuilder
  -> structured ReasoningEngine
  -> backend policy validation
  -> ToolRegistry execution / durable confirmation
  -> grounded streaming response
  -> bounded incremental TTS (voice only)
  -> terminal persistence and metrics
```

Every Phase 10 integration assertion follows this direction. Direct calls to a
domain service are permitted for its unit tests, never as evidence that a
conversation capability uses the production execution path.

## Failure and resilience rules

- Cancellation must close producer and consumer tasks and persist no partial AI
  response.
- Provider failure after a visible delta must not append or speak a duplicated
  fallback response.
- TTS failure must preserve the full text terminal event and drain bounded work.
- Unknown tools, extra arguments, cross-user identifiers, expired confirmation,
  and forward dependencies must execute no handler.
- One failed tool stops dependent calls and cannot be represented as success.
- Concurrent turns must preserve event order and user/conversation isolation.
- Database and embedding failures must fail closed rather than scanning all
  memories or silently switching to an unbounded search.

## Non-functional budgets

Budgets below measure architecture overhead with external provider time excluded:

- state cache load p95: less than 25 ms;
- memory query p95: less than 250 ms on the PostgreSQL regression corpus;
- prompt build p95: less than 10 ms;
- reasoning contract validation p95: less than 10 ms;
- tool registry validation p95: less than 10 ms;
- response segmentation p95: less than 2 ms;
- event forwarding p95: less than 10 ms;
- cancellation propagation: less than 100 ms;
- mixed deterministic turns: zero errors and zero identity/event leakage.

Deployment providers have separate mandatory SLOs because deterministic tests
cannot represent network and model capacity. A release environment must set and
enforce first-token, first-audio, error-rate, and saturation thresholds before a
canary receives traffic. The measured local CPU Ollama and local WAV providers
are compatibility targets, not approved production-latency targets.

## CI and release policy

The normal API job runs lint, the complete deterministic suite, and the Phase 10
gate. A separate PostgreSQL service job applies migrations and runs the pgvector
integration test with its skip guard explicitly enabled. Flutter analysis and
tests remain required because WebSocket event and audio contracts terminate in
the mobile client.

Deployment should remain behind the existing streaming/reasoning rollout flags.
Canary promotion requires healthy error, cancellation, first-token, first-audio,
and queue-depth metrics. Rollback is code/config only for Phases 6–10; the Phase
5 schema is backward-compatible and must not be destructively rolled back.

## Architecture approval

- One-brain invariant: approved.
- Test boundaries and dependency direction: approved.
- Security and failure policy: approved.
- Load and latency budgets: approved.
- CI/database gate design: approved.
- Rollout and rollback design: approved.

Implementation must prove this document before the gate can be approved.

## Phase 10 completion report

### Files changed

- `.github/workflows/api-ci.yml` — lint, compile, dependency consistency,
  vulnerability audit, deterministic regression, clean PostgreSQL migration,
  and pgvector/HNSW jobs are explicit release gates.
- `apps/api/tests/test_quality_phase10.py` — auditable category manifest,
  text-to-voice multi-turn continuity, state uniqueness, calendar/task registry
  convergence, and dependent-tool failure containment.
- `apps/api/requirements.txt`, `app/auth.py`, and `app/routers/ws_session.py` —
  upgraded the FastAPI/Starlette security boundary, upgraded
  `pydantic-settings`, replaced the `python-jose`/`ecdsa` dependency chain with
  PyJWT plus cryptography, and added Starlette's maintained HTTPX2 test client.
- `apps/api/tests/conftest.py` — uses an RFC-appropriate test HMAC key length.
- Stale imports and two unused locals were removed mechanically from the
  routers, services, and tests reported by the existing Ruff gate. This changes
  no runtime branch and makes the repository's configured lint command pass.
- This document — quality architecture, evidence, risks, manual checks, and the
  combined Phase 5–10 approval record.

### Architecture and integration review

- The quality work adds no feature router, model brain, prompt, memory path, or
  tool executor.
- REST text and live voice were exercised across two turns in one conversation;
  both reached the same reasoning engine and immutable registry, retained the
  first turn in the second reasoning envelope, and produced exactly one durable
  state record.
- Calendar and task reads executed through `ToolRegistry.execute` with their
  authenticated text/voice sources intact.
- A failed first tool produced a failed terminal action, stopped its dependent
  call, exposed grounded validation evidence, and did not report false success.
- The full migration chain applies from an empty PostgreSQL database through
  `20260715_0017_phase5_memory_index`; vector backfill, bounded semantic search,
  HNSW execution-plan use, and the Phase 5 latency assertion pass on PostgreSQL.

### Security review

- Backend identity, confirmation, argument, and user-scope policies remain
  deterministic and fail closed.
- FastAPI `0.139.x`, Starlette `1.3.x`, pydantic-settings `2.14.2+`, PyJWT
  `2.13.x`, and cryptography replace the vulnerable dependency set found during
  Phase 10 review.
- `pip check`: no broken requirements.
- `pip-audit --local`: no known vulnerabilities in the final environment.
- CI upgrades build tooling before scanning so known pip/setuptools advisories
  cannot be hidden by an otherwise clean application dependency set.

### Verification completed

- Phase 5–10 focused regression: `51 passed`.
- Phase 10 focused suite: `3 passed`.
- Final full API suite on the remediated dependency set: `283 passed, 1 skipped`
  in `44.13 s`; the only skip is the deliberately environment-gated PostgreSQL
  test that passed separately.
- Isolated PostgreSQL/pgvector gate: `1 passed` in `9.55 s` after a clean
  revision-zero migration to head.
- Conversation-state/WebSocket compatibility after FastAPI/Starlette/HTTPX2
  upgrade: `23 passed` with no deprecation warning.
- Flutter regression: `13 passed`; Flutter analysis: no issues.
- Ruff over application and tests: clean.
- Python compile, workflow YAML parse, dependency consistency, migration-head,
  and repository diff checks: clean.
- Final vulnerability audit: no known vulnerabilities.

### Latency and load evidence

- Phase 5 PostgreSQL semantic retrieval p95 remains below `250 ms` on the
  400-document gate corpus; 20 concurrent deterministic retrievals remain
  bounded.
- Phase 6 prompt construction, Phase 7 contract validation, and Phase 8
  registry validation remain below their `10 ms` p95 budgets.
- Phase 8 completed 250 isolated concurrent tool executions without context
  leakage.
- Phase 9 completed 100 concurrent streams with ordered chunks; segmentation
  p95 is `0.0022 ms`, event forwarding p95 `0.0012 ms`, and internal
  cancellation propagation remains below `100 ms`.
- The Phase 10 cross-modality integration retains ordered messages and one state
  record across reconnect-compatible request boundaries.

### Manual verification and deployment checklist

1. Run the CI deterministic and PostgreSQL jobs on the release commit.
2. Before upgrading an existing environment, compare `alembic current` with the
   physical schema. The old local development volume had a pre-existing
   `tts_voice` column while stamped before that migration; a fresh database
   migrated cleanly. Resolve any target drift explicitly rather than stamping
   over it.
3. Preload the production embedding model, run the memory backfill, and verify
   every user completes without an error.
4. Exercise text, live voice, uploaded audio, a planner confirmation across
   reconnect, calendar/task reads, barge-in, and a forced provider/TTS failure
   in staging.
5. Canary the configured LLM and TTS providers only after measured first-token,
   first-audio, error-rate, queue-depth, and cancellation SLOs pass.
6. Confirm mobile playback on a physical target device; this workstation had no
   attached device for acoustic microphone/speaker verification.

### Remaining risks and known limitations

- The CPU-only local Ollama compatibility target measured roughly `35.5 s` to
  first token and is not approved for production voice latency.
- Local WAV synthesis measured roughly `1.8 s` for one phrase and is not the
  production first-audio target.
- Production-scale HNSW recall/capacity, target database drift, provider
  saturation, and physical-device acoustic behavior are deployment-environment
  gates; they cannot be certified by deterministic repository tests.
- Structured reasoning intentionally completes before tool authorization;
  incomplete JSON is never streamed into the execution policy.

### Combined Phase 5–10 approval

| Phase | Implementation | Integration | Quality gate | Approval |
| --- | --- | --- | --- | --- |
| 5 Memory | complete | PostgreSQL/vector path verified | semantic, isolation, load, HNSW | approved |
| 6 Prompt | complete | one canonical builder verified | injection, size, latency | approved |
| 7 Reasoning | complete | structured reason/validate/execute/final loop | multi-intent, confirmation, failure | approved |
| 8 Tools | complete | one immutable registry for all inputs | auth scope, load, anti-bypass | approved |
| 9 Streaming | complete | provider deltas to bounded incremental TTS | order, backpressure, interruption | approved for integration |
| 10 Quality | complete | CI, database, mobile, security gates | full regression and audit green | approved |

Combined code implementation and production integration readiness for Phases
5–10: **approved**. Traffic rollout remains blocked until the selected production
LLM/TTS providers, target database preflight, and physical-device voice smoke
meet the documented deployment gates.
