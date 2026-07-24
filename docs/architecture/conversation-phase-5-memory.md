# Phase 5 — Unified Memory Architecture

Status: production-ready. Phase 6 may begin.

## Invariants

- The conversation orchestrator has one `MemoryManager` for text, REST, live voice, uploaded audio, and future modalities.
- Speech-start retrieval contains only stable context and never guesses from an incomplete transcript.
- Every final transcript performs a fresh query-specific semantic retrieval.
- Retrieval is user-scoped, visibility-filtered, bounded, and deduplicated.
- Source tables remain authoritative. `memory_search_documents` is a rebuildable projection.
- Live retrieval never scans all memories. Existing data is indexed by the deployment backfill.

## Data and execution flow

```text
source writes ──> source tables ──> MemoryManager.index_row ──> semantic projection
                                                                  │
speech_started ──> retrieve_stable ──> cached voice preload       │
                                                                  │
final_transcript ──> retrieve_query ──> pgvector HNSW ────────────┘
                            │
                            └─> bounded LSH/cosine fallback (SQLite only)

stable context + query context ──> merge/dedupe ──> one conversation brain
```

## Retrieval sequence

```text
Voice transport      Conversation orchestrator       MemoryManager          LLM path
      |                         |                          |                    |
      | speech detected         |                          |                    |
      |------------------------>| retrieve_stable          |                    |
      |                         |------------------------->|                    |
      |                         |<-------------------------|                    |
      | final transcript        |                          |                    |
      |------------------------>| retrieve_query(text)     |                    |
      |                         |------------------------->| vector candidates  |
      |                         |<-------------------------|                    |
      |                         | merge + dedupe            |                    |
      |                         |----------------------------------------------->|
```

Text and REST enter at the same orchestrator. They execute both stages after input acceptance because there is no speech interval available for preloading.

## Indexed domains

The semantic projection covers long-term memories, projects and project events, people, relationships, knowledge entities and edges, goals, tasks, reminders, calendar items, Today items, and the 100 most recent discussion messages per user. Stable retrieval separately loads the current profile, active projects/goals/tasks, people/relationships, today's calendar/agenda/reminders, recent discussion, and important long-term memory using bounded database queries.

## Search backends

- PostgreSQL: `vector(1536)` with an HNSW cosine index.
- SQLite tests/development: four indexed locality-sensitive hash bands select at most 160 candidates, followed by cosine reranking.
- Embeddings: local FastEmbed (`BAAI/bge-small-en-v1.5`) by default; OpenAI-compatible and Ollama providers are supported. Provider output is normalized and padded to 1536 dimensions.
- Production is fail-closed if semantic embeddings are unavailable. The deterministic embedding exists only as an explicit test/development fallback.

## Deployment

1. Install `requirements.txt`.
2. Run `alembic upgrade head`.
3. Run `python scripts/preload_embedding_model.py`.
4. Run `python scripts/backfill_memory_index.py` before serving production traffic.
5. Confirm the backfill reports every user and exits successfully.
6. Verify `memory_context_ready` metrics and PostgreSQL query plans use `ix_memory_search_documents_embedding_hnsw`.

The production playbook enforces migration, model preload, and backfill in that
order before the service is restarted. PostgreSQL migration failures are
fail-closed; Alembic never reports success by migrating an unrelated SQLite
database.

The backfill is idempotent through `memory_index_status`. New and updated records are indexed by their owning domain services; deleted records remove their projection.

## Latency budgets

- Stable retrieval: under 100 ms p95 against the production database.
- Query embedding plus HNSW retrieval: under 250 ms p95 with the local embedding model warm.
- SQLite fallback regression budget: under 150 ms p95 with 400 indexed records.
- Candidate count is bounded to 160 outside PostgreSQL and to `max(limit * 4, 40)` with pgvector.

## Operational risks

- The local FastEmbed model must be downloaded during image build or deployment, not on the first user turn.
- Backfill completion is a deployment gate for pre-existing data.
- PostgreSQL must have the `vector` extension installed before the migration.
- Embedding/index write failures need monitoring; source data remains authoritative and the index can be rebuilt.

## Phase 5 completion report

### Files changed

- `app/services/memory_manager.py`, `app/services/embedding_service.py`, and
  `app/conversation/ports.py`: unified retrieval, semantic embedding, bounded
  fallback ranking, and the memory contract.
- `app/models.py`, `migrations/versions/20260715_0017_phase5_memory_index.py`,
  `scripts/backfill_memory_index.py`, and `scripts/preload_embedding_model.py`:
  semantic projection, vector index, migration, idempotent deployment backfill,
  and cold-model validation.
- `migrations/env.py`, the baseline migration, and `infra/playbooks/deploy-v2.yml`:
  clean PostgreSQL bootstrap, fail-closed migrations, and ordered rollout gates.
- `app/services/companion_orchestrator.py` and `app/services/voice_turn.py`:
  speech-start stable preload and final-transcript query retrieval through the
  same conversation brain.
- Domain write services for projects, people/knowledge, goals, tasks,
  reminders, calendar, Today, memories, and conversation messages: projection
  lifecycle updates.
- `tests/test_memory_manager_phase5.py`: domain coverage, bounded retrieval,
  lifecycle, isolation, load, latency, and production failure tests.

### Architecture and latency impact

The former full-memory scan is no longer part of a conversation turn. Source
tables remain authoritative and one rebuildable, user-scoped semantic
projection serves every modality. SQLite fallback ranking decodes and scores
vectors off the event loop, fetches full documents only after ranking, and
coalesces identical concurrent fallback requests. PostgreSQL continues to use
pgvector HNSW directly. The automated budgets enforce under 150 ms p95 for a
400-document SQLite index and under 500 ms for 20 concurrent identical
fallback requests.

### Verification completed

- Phase 1–5 focused tests: passed.
- Full API regression suite: `242 passed, 1 skipped` (the opt-in PostgreSQL
  integration test is excluded from the SQLite default suite).
- Mobile analysis: no issues.
- Mobile tests: `13 passed`.
- Phase 5 Python lint scope: passed.
- Clean PostgreSQL/pgvector Alembic upgrade through revision
  `20260715_0017`: passed.
- Direct backfill command against the migrated PostgreSQL database: passed.
- PostgreSQL backfill/retrieval/latency integration: passed (`400` documents,
  warm p95 under `250 ms`).
- Forced PostgreSQL query plan confirmed
  `ix_memory_search_documents_embedding_hnsw`: passed.
- WebSocket voice transport and interruption suites: passed. No physical mobile
  device was attached to this workstation, so device microphone/acoustic
  behavior remains a release-environment smoke test rather than a code gate.

### Manual production verification

1. Build the image with the configured embedding model already present.
2. Upgrade a PostgreSQL staging database and confirm the `vector` extension and
   `ix_memory_search_documents_embedding_hnsw` exist.
3. Run `python scripts/backfill_memory_index.py`; require a successful line for
   every user and a zero exit status.
4. Start a live voice turn and confirm stable context is ready during speech,
   then confirm query-specific memory metrics appear only after final STT.
5. Repeat the same query through text and uploaded audio and compare retrieved
   source IDs.
6. Update and delete one item in every indexed domain, then verify no stale
   projection remains.

### Remaining risks and known limitations

- Production-scale HNSW recall and capacity still require staging measurements;
  the isolated PostgreSQL gate proves compatibility and the latency budget at
  the 400-document regression scale.
- Embedding provider and index-write failures require alerts and a scheduled
  reconciliation/backfill runbook.
- The configured FastEmbed model must be cached on each deployment target. The
  playbook now fails before restart when preload cannot produce a valid vector.

### Production readiness checklist

- [x] Implementation complete
- [x] Code review
- [x] Integration review
- [x] Architecture review
- [x] Edge-case review
- [x] Regression tests
- [x] Latency and concurrent-load tests
- [x] Migration and backfill verification
- [x] PostgreSQL pgvector/HNSW/explain verification
- [x] Manual-equivalent WebSocket/reconnect/interruption verification
- [x] Production embedding preload enforced before service restart

Phase 5 is complete. Deployment still requires the ordinary target-specific
model preload and live-device smoke check; both fail or block rollout without
creating a second conversation path.
