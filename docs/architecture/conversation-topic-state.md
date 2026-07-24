# Semantic Topic State

Workstream 3 replaces passive lexical topic metadata with one canonical,
backend-authoritative semantic topic-transition system. It is shared by text,
live voice, and uploaded-audio turns through `ConversationOrchestrator`.

## Active flow

```text
User turn
→ semantic endpoint completion
→ transcript final
→ canonical state load
→ semantic topic transition
→ state-policy validation
→ atomic topic-state update
→ unified orchestrator
→ transition-selected context
→ reasoning and tools
```

Topic classification occurs after final transcript creation and before the brain
adapter can reason, resolve a confirmation, or execute tools. The endpoint
detector's former lexical `topic_changed` value has no orchestration authority.

## Transition contract

`TopicTransitionDecision` has stable classifications:

- `continue_same_topic`
- `refine_current_request`
- `modify_active_request`
- `correct_previous_detail`
- `add_related_request`
- `new_related_subtopic`
- `new_unrelated_topic`
- `resume_previous_topic`
- `cancel_active_request`
- `reject_pending_action`
- `confirm_pending_action`
- `ambiguous_transition`

The contract carries confidence, a concise reason code, current/previous/target
topic IDs, goal and intent, context/pending-action policy flags, changed
entities, model version, turn ID, state version, pending action ID, transition
sequence, classifier latency, and any fallback reason. It contains no hidden
reasoning.

## Canonical state and atomicity

The existing `ConversationState` facade now owns `active_topic`, bounded
`topic_history`, and `topic_transition_sequence`. `TopicState` records a stable
ID, type, title, goal, status, timestamps, last turn, language, entities,
pending-action ID, parent/related IDs, resume count, and summary. Status is one
of active, paused, completed, cancelled, superseded, awaiting confirmation, or
awaiting information.

State remains in the existing PostgreSQL JSON record and Redis-compatible cache.
Optimistic version comparison makes transition and pending-action changes
atomic across workers. No second worker-local topic store or migration was
introduced. Processed turn IDs are bounded and duplicate user events are
rejected before reasoning or tool execution.

## Model and features

The active provider is `semantic-local`, using the same
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` FastEmbed ONNX
model as multilingual endpointing. It compares the current utterance with the
active and up to five recent paused topics. It also uses semantic intent
prototypes, active/previous goals, pending fields, extracted time/date changes,
missing-information state, language, and code-switch-compatible Unicode text.
Explicit cancel, confirm, reject, continue, correction, and resume expressions
are bounded backend safety signals rather than the primary classifier.

Active-topic vectors are cached in a bounded 128-entry process cache; durable
state remains authoritative. Development-host measurements after preload were
approximately 5 ms median and 9 ms p95, with a roughly 1.7–2.3 second cached
model preload.

## Orchestration policy

- Continue/refine/modify/correct retains the topic ID and valid draft, merges
  structured entity changes, and avoids duplicate actions.
- Related requests retain the relationship; a related subtopic pauses the
  parent and creates a child topic.
- An unrelated topic pauses the old topic and clears its pending action and
  confirmation before reasoning receives state.
- Resume selects a semantically matching paused topic, increments its resume
  count, and never restores an expired confirmation or replays a tool call.
- Cancel/reject clears only the active request's pending state.
- Ambiguous, unavailable, malformed, low-margin, or timed-out classification
  executes nothing and returns one concise clarification.

The brain adapter receives the policy-filtered state. Topic-specific pending
fields are therefore absent from prompts for unrelated turns.

## Confirmation safety

Every new confirmation is bound to action ID, topic ID, originating turn ID,
user ID, conversation ID, requested time, and expiry. Confirmation is accepted
only when every binding still matches the active state and neither the action
nor confirmation has expired. Unrelated transitions invalidate the binding by
clearing pending state. A later `yes` cannot execute the old action.

## Validation corpus and metrics

The regression corpus contains 250 scenarios across English, Nigerian English,
Nigerian Pidgin, English/Pidgin code-switching, and French. Distribution is
40 continue, 35 refine, 35 modify, 30 correct, 25 add-related, 20 related
subtopic, 25 unrelated, 20 resume, 10 cancel, and 10 ambiguous cases. It covers
low lexical overlap/same topic, high overlap/new intent, stale confirmation,
pronouns, correction, changed times, multi-intent, semantic resume, duplicate
events, cancellation, and ambiguous candidates.

The calibrated semantic-feature corpus achieved 100% overall and per-class
classification at the safety boundary, zero unsafe pending preservation, zero
incorrect cancellation, 100% stale-confirmation rejection, 100% resume and
correction accuracy, and zero fallback on controlled non-ambiguous cases. Real
model smoke tests cover semantic intent separation and measured inference
latency. These are automated development-host results, not staging or real-user
evidence.

## Configuration and fallback

Configuration controls provider, model, version, device, confidence/margin,
timeout, paused-topic limit, topic/confirmation expiry, similarity thresholds,
fallback mode, production fallback policy, and diagnostics. Startup and the
deployment preload script validate the model. Production `fail_closed` rejects
an unavailable classifier. Runtime failure returns `ambiguous_transition` with
an explicit reason and preserves state safely; production never silently falls
back to lexical overlap.

## Remaining limitations

Real-user conversation validation, staging concurrency, production multi-worker
validation, broader language evaluation, and physical-device conversational
testing remain required. Workstream 4 and later work are not started.
