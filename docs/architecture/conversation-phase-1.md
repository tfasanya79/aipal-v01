# Phase 1: Unified Conversation Architecture

Status: implemented. This document describes the Phase 1 boundary only. The
state, voice, turn-detection, memory, prompt, reasoning, tool, and true-streaming
internals remain compatibility implementations until their approved phases.

## Component flow

```mermaid
flowchart LR
  T[REST text] --> N[ConversationInput]
  A[Uploaded audio after STT] --> N
  V[Live voice final transcript] --> N
  F[Future modality adapter] --> N
  N --> O[ConversationOrchestrator]
  O --> B[ConversationBrainPort]
  B --> L[LegacyCompanionBrainAdapter]
  L --> C[Current CompanionOrchestrator]
  C --> P[Current context, memory, prompt, LLM and tools]
  P --> E[ConversationEvent stream]
  E --> R[REST result collector]
  E --> W[WebSocket and TTS transport]
```

## Turn sequence

```mermaid
sequenceDiagram
  participant U as User transport
  participant N as Input adapter
  participant O as ConversationOrchestrator
  participant B as Brain port
  participant S as Current subsystems
  U->>N: text or final transcript
  N->>O: ConversationInput v1
  O-->>U: input_accepted
  O->>B: stream(input, runtime context)
  B->>S: one current turn implementation
  S-->>B: result
  B-->>O: context/reply/sentence/complete
  O-->>U: ordered ConversationEvent v1
```

## Dependency rule

```mermaid
flowchart TD
  Routers[HTTP and WebSocket routers] --> Facade[conversation.service]
  Facade --> Contracts[contracts]
  Facade --> Root[composition root]
  Root --> Orchestrator[ConversationOrchestrator]
  Orchestrator --> Ports[conversation ports]
  Root --> Adapter[legacy brain adapter]
  Adapter --> Existing[existing companion implementation]
```

Routers may authenticate, validate, rate-limit, transcribe, synthesize, and map
wire formats. They may not select prompts, memory, planners, tools, or LLMs.

## State machine

```mermaid
stateDiagram-v2
  [*] --> Accepted
  Accepted --> Reasoning
  Accepted --> Cancelled: cancellation
  Reasoning --> Responding: reply event
  Reasoning --> Cancelled: cancellation
  Responding --> Completed: terminal event
  Responding --> Cancelled: interruption
  Completed --> [*]
  Cancelled --> [*]
```

## Contract guarantees

- Every input has schema, input, turn, user, conversation, modality, and time metadata.
- Every event has a unique ID, ordered sequence, correlation/causation IDs, and transient/durable classification.
- Authenticated user identity is checked at the orchestration boundary.
- REST collection consumes the same event stream used by live transports.
- Cancellation is checked before execution and between emitted events.
- Free-form language cannot invoke the compatibility tool router by keyword;
  explicit trusted UI tool context remains supported.
