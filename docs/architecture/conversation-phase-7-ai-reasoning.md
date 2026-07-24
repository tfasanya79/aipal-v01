# Phase 7 — Structured AI Reasoning Engine

Status: production-ready. Phase 8 is not started.

## Decision

Every free-form conversation turn uses one model-driven reasoning cycle before
the backend selects or executes a capability. Explicit UI commands remain
deterministic because the user already selected the operation; authentication,
authorization, safety, validation, confirmation, and persistence remain backend
owned.

Legacy keyword, regex, phrase, and mode routing is retained only as a bounded
compatibility fallback when the configured model is unavailable or returns an
invalid contract. It is never the primary production reasoning path.

## Service boundaries

```text
Conversation Orchestrator
        |
        +--> Conversation State + two-stage Memory Manager
        |
        v
Canonical PromptBuilder (purpose=reasoning)
        |
        v
LLM --> strict ReasoningDecision JSON
        |
        v
Reasoning Contract Validator
  - schema and size limits
  - allowlisted tools and arguments
  - user ownership / permissions
  - confirmation policy
  - pending-action consistency
        |
        v
Ordered Tool Executor Adapter
  - executes validated calls only
  - returns bounded structured results
        |
        v
Canonical PromptBuilder (purpose=final_response)
        |
        v
LLM --> user-facing answer --> persist state/messages/events
```

Phase 8 will replace the compatibility executor adapter with the authoritative
Tool Registry. Phase 7 does not create a second registry or bypass the existing
tool boundary.

## Reasoning contract

The model returns strict JSON with:

- one or more intents with confidence;
- mode and emotion assessment;
- missing information;
- conversation and response strategy;
- ordered tool calls with bounded arguments and rationale;
- planning notes and dependency ordering;
- requested confirmation behavior;
- pending-action resolution (`none`, `confirm`, or `discard`).

The contract contains no chain-of-thought field. Rationales are short audit-safe
justifications, not hidden reasoning traces.

## Confirmation state machine

```text
validated read call -------------------------------> execute
validated draft-producing call --------------------> execute draft
                                                     -> await confirmation to apply
validated mutation without prior confirmation ----> persist pending action
                                                     -> ask confirmation
next-turn confirm + matching durable pending action -> execute
next-turn discard + matching durable pending action -> clear without execution
expired/mismatched pending action ------------------> reject safely
```

The backend calculates confirmation requirements. A model-provided flag may be
more conservative but can never waive backend policy.

## Failure and resilience rules

- Malformed, oversized, unknown-tool, or unsafe reasoning output is rejected.
- Partial tool execution stops after the first failure; subsequent dependent
  calls are not attempted.
- Tool results are bounded before entering the final prompt.
- Model or validation failure may use the existing deterministic compatibility
  path, with a metric identifying the fallback.
- No mutation is retried automatically.
- Cancellation is checked between reasoning, each tool call, and final response.

## Observability

Each turn records bounded metrics and metadata:

- reasoning latency and validation status;
- selected intents, tools, and ordering;
- confirmation decisions;
- tool duration and result status;
- final-response latency;
- fallback reason, without prompts, secrets, or hidden reasoning.

## Non-functional budgets

- contract validation: under 10 ms p95;
- orchestration overhead excluding LLM/tool I/O: under 30 ms p95;
- maximum four ordered tool calls per turn;
- maximum 20 arguments and a 12 KB serialized argument envelope per call;
- maximum 16 KB of bounded tool evidence in the final prompt.

## Architecture approval

- Service boundaries: approved.
- Structured contract and validation boundary: approved.
- Confirmation and pending-action lifecycle: approved.
- Failure isolation and observability: approved.
- Phase boundary: approved; Tool Registry consolidation remains Phase 8.

## Phase 7 completion report

### Files changed

- `app/conversation/reasoning.py`: versioned multi-intent decision, emotion,
  ordered tool-call, pending-resolution, and metrics contracts.
- `app/services/ai_reasoning_engine.py`: canonical reasoning prompt, strict JSON
  parsing, schema validation, and grounded final-response pass.
- `app/services/reasoning_policy.py`: tool allowlist, argument schemas, size and
  ownership boundaries, dependency checks, and backend confirmation policy.
- `app/services/reasoned_turn_service.py`: two-stage memory context, reasoning,
  ordered execution, failure isolation, final response, message persistence,
  and reasoning observability.
- `app/services/companion_orchestrator.py`: model reasoning is now the primary
  free-form path; phrase and regex behavior is compatibility fallback only.
- `app/services/tool_router.py`: existing tools can return raw validated results
  without an intermediate narration LLM call.
- `app/services/prompt_builder.py`: the one canonical template now supports
  internal reasoning and final-response purposes without introducing another
  prompt authority.
- `app/llm_provider.py`: provider-native structured outputs for Ollama and
  OpenAI-compatible models, JSON mode for DeepSeek, and bounded reasoning token
  and timeout overrides.
- `app/conversation/state.py`: durable pending tool calls survive reconnects and
  can be confirmed only when they match the stored action.
- `app/config.py`, `.env.example`, and `tests/conftest.py`: production-default
  rollout controls and deterministic test isolation.
- `tests/test_ai_reasoning_phase7.py`: contract, security, multi-intent,
  ordering, latency, tool-result, fallback, planner, mutation confirmation, and
  text/voice integration coverage.

### Architecture impact

Free-form user language no longer enters backend keyword routing as the primary
decision mechanism. The LLM selects intent, multiple intents, missing details,
mode, conversation strategy, response strategy, tool order, and conservative
confirmation intent in a strict contract. The backend can reject or strengthen
that plan but cannot invent a competing semantic route. Explicit UI-selected
commands remain deterministic.

The execution adapter deliberately remains over the current tool boundary.
Phase 8 will make the Tool Registry authoritative without changing the Phase 7
reasoning contract.

### Latency impact

- Pydantic contract parsing plus backend policy validation: `0.034 ms` p95
  across 1,000 local iterations.
- Validation production budget: under `10 ms` p95.
- Tool calls are capped at four, arguments at 20 fields/12 KB, and final tool
  evidence at four bounded results.
- The local CPU-only `llama3.2:3b` structured-output smoke completed in about
  `59.6 seconds`; this proves provider compatibility, not an acceptable voice
  latency. Production voice requires a low-latency hosted model or accelerated
  local inference. Phase 9 owns response streaming, not reasoning-model speed.

### Verification completed

- Phase 7 focused tests: `10 passed`.
- Phase 6/7 boundary and provider-policy tests: passed.
- Full API regression suite: `259 passed, 1 skipped`; the skipped test is the
  opt-in PostgreSQL Phase 5 integration gate, which passed separately.
- Flutter analysis: no issues.
- Flutter tests: `13 passed`.
- Python lint and repository diff checks: passed.
- Live Ollama structured-output smoke: passed with a schema-valid multi-intent
  `ReasoningDecision`.
- Planner draft -> durable confirmation -> Today application: passed.
- Project-room mutation -> durable confirmation -> execution: passed.
- Malformed contract -> measured compatibility fallback: passed.

### Manual verification steps

1. Configure the production reasoning model and send a compound request such as
   “show today, check my tasks, and help me choose what comes first.” Confirm one
   reasoning call contains multiple intents and ordered tool calls.
2. Capture the final model request and confirm it occurs only after validated
   tool results are available.
3. Request a mutation, reconnect before replying, then confirm it. Verify the
   stored call executes once and a mismatched or expired confirmation cannot run.
4. Return malformed JSON, an unknown tool, cross-user identifiers, oversized
   arguments, and forward dependencies from a test model. Confirm each is
   rejected without mutation.
5. Repeat equivalent requests through REST text, WebSocket text, live voice,
   and uploaded audio; confirm all reach `reason_about_turn` through the same
   orchestrator.
6. Monitor `reasoning_ms`, `validation_ms`, `tool_execution_ms`,
   `final_response_ms`, `total_ms`, and compatibility fallback reasons.

### Remaining risks and known limitations

- The compatibility executor still exposes the existing tool switch. Phase 8
  must replace it with one authoritative Tool Registry.
- The local 3B CPU model is too slow for production voice despite validating the
  contract correctly; deployment must select and latency-test an appropriate
  reasoning model.
- DeepSeek JSON mode constrains output to JSON but does not enforce the complete
  schema server-side; backend Pydantic validation remains mandatory.
- Compatibility keyword/regex logic remains available only when reasoning is
  disabled, unavailable, or invalid. Fallback rates should be alerted because a
  rising rate means the AI reasoning path is unhealthy.
- Phase 9 will stream final responses; Phase 7 intentionally performs the full
  reasoning decision before any tool or answer is emitted.

### Production readiness checklist

- [x] Implementation complete
- [x] Code review
- [x] Integration review
- [x] Architecture review
- [x] Edge-case and security review
- [x] Regression tests
- [x] Contract and orchestration latency tests
- [x] Manual configured-model verification
- [x] Durable confirmation and reconnect verification
- [x] Production readiness review

Phase 7 is complete. Do not begin Phase 8 until its Tool Registry architecture
review is approved.
