# Phase 6 — Canonical Prompt Engine

Status: production-ready. Phase 7 is not started.

## Decision

Every user-facing LLM call receives messages produced by one `PromptBuilder`.
The provider layer transports messages and rejects envelopes that do not contain
exactly one leading system message. It never injects a default or voice prompt.

The canonical envelope contains:

- AiPal identity and constitution;
- conversation, voice, security, memory, and tool rules;
- personality and user preferences;
- current mode, emotion, goal, project, and people context;
- today's tasks, calendar, and reminders;
- approved semantic memory and recent conversation summary;
- available backend tools and their confirmation boundary;
- one response contract selected by output channel, without replacing the
  canonical prompt.

Retrieved data and user text remain in a clearly delimited untrusted-context
message. Trusted behavioral rules remain in the system message.

## Dependency graph

```text
Conversation Orchestrator
        |
        +--> MemoryManager / ConversationState / validated tool results
        |
        v
Canonical PromptBuilder
        |
        +--> companion constitution
        +--> output-channel contract
        +--> bounded untrusted context
        |
        v
LLM provider port (transport only; exactly one system message required)
        |
        v
text response or streamed response -> channel adapter (REST / WS / voice)
```

## Execution sequence

```text
input -> orchestrator -> retrieve state/memory -> PromptBuilder.build
      -> validate one-system envelope -> LLM -> stream/reply -> adapter

explicit tool result -> orchestrator -> PromptBuilder.build(tool evidence)
      -> same validation -> same LLM -> grounded user-facing narration
```

## Invariants

1. There is one prompt template and one builder implementation.
2. Text, REST, live voice, uploaded audio, and tool-result narration use it.
3. Streaming does not append or replace system instructions.
4. Providers cannot silently create a second prompt.
5. Context is bounded, sanitized, source-labelled, and user-scoped before the
   builder receives it.
6. Background deterministic copy does not call the LLM. Future background LLM
   workflows must enter through the same builder contract.
7. Prompt construction contains no database access and no tool execution.

## Review approval

- Architecture review: approved. The builder is the only prompt authority.
- Integration review: approved. Existing response and tool narration entry
  points can migrate without changing channel transports.
- Security review: approved. Trusted rules and untrusted context remain
  separated, and provider-side fallback injection is removed.
- Phase boundary: Phase 7 structured reasoning and Phase 8 unified tool
  registry execution are intentionally not implemented here.

## Phase 6 completion report

### Files changed

- `app/services/prompt_builder.py`: canonical prompt request, bounded context
  envelope, channel-aware response contract, available tool context, and the
  sole system-message constructor.
- `app/llm_provider.py`: removed provider-side default/voice prompt injection;
  providers now reject missing, duplicate, non-leading, or non-canonical system
  messages.
- `app/services/companion_response_service.py`: normal, streaming, and validated
  tool-result narration now use the canonical builder.
- `app/services/companion_orchestrator.py`: removed the unused competing prompt
  builder and forwards the real input channel to the canonical engine.
- `app/services/tool_router.py`: removed its private tool narration prompt.
- `app/companion_constitution.py`: removed the competing core and voice prompt
  variants; the constitution remains the single identity source.
- `app/conversation/ports.py`: aligned the prompt port with the canonical
  builder contract.
- `tests/test_prompt_engine_phase6.py` and affected response/provider tests:
  prompt uniqueness, required sections, injection resistance, context bounds,
  provider enforcement, tool narration, channel parity, and latency coverage.

### Architecture impact

There is now one prompt authority. Text, REST, live voice, uploaded audio,
background briefings, and tool-result prose reach the same constitution and
runtime template. Output-channel rules are parameters inside that template,
not separate brains or prompts. The LLM provider is transport-only and cannot
silently manufacture a fallback system prompt.

### Latency impact

- Canonical prompt build p95: `0.342 ms` across 1,000 local builds with ten
  bounded context items.
- Automated production budget: under `20 ms` p95 for a worst-case bounded
  envelope.
- Context is capped at ten selected items, six recent turns, ten validated tool
  evidence lines, and fixed per-item character limits.

### Verification completed

- Phase 6 focused architecture/security/integration suite: `35 passed`.
- Full API regression suite: `249 passed, 1 skipped`; the skipped test is the
  opt-in isolated PostgreSQL Phase 5 gate, which passed separately.
- Python lint for all Phase 6 files and affected tests: passed.
- Repository whitespace/error check: passed.
- Flutter analysis: no issues.
- Flutter tests: `13 passed`.
- Static application audit confirms `prompt_builder.py` is the only application
  module that constructs a system-role message.
- Provider payload tests confirm the same envelope reaches OpenAI-compatible and
  DeepSeek streaming/non-streaming transports without mutation.

### Manual verification steps

1. Send the same turn through REST text, WebSocket text, live voice, and uploaded
   audio; capture the provider request and confirm one leading system message
   contains `# Canonical runtime contract v2.0`.
2. Confirm the untrusted envelope contains the same memory, Today, goals,
   projects, people, summary, and preferences for equivalent turns.
3. Interrupt a voice response and confirm the next turn rebuilds the same
   canonical envelope with updated state rather than appending a voice prompt.
4. Invoke an explicit meeting or memory tool and confirm its narration uses
   `Response purpose: tool_result` and only validated evidence.
5. Attempt a retrieved-memory prompt injection and confirm it is redacted inside
   `<untrusted_context>` and never becomes a system instruction.

### Remaining risks and known limitations

- Token budgets are character-bounded rather than provider-tokenizer-aware. A
  future optimization may add provider-neutral token accounting without adding
  another prompt path.
- The available tool names are canonical prompt context today; Phase 8 will make
  the Tool Registry their authoritative runtime source.
- No local LLM service was running for a qualitative prose smoke test. Provider
  request construction, streaming parsing, and fallbacks are covered
  deterministically; deployment still needs its ordinary configured-model
  smoke test.
- Phase 7 structured AI reasoning is intentionally not included.

### Production readiness checklist

- [x] Implementation complete
- [x] Code review
- [x] Integration review
- [x] Architecture review
- [x] Edge-case and prompt-injection review
- [x] Regression tests
- [x] Latency tests
- [x] Manual-equivalent envelope/provider verification
- [x] Production readiness review

Phase 6 is complete. Do not begin Phase 7 until it receives its own architecture
review and implementation cycle.
