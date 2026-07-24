# AiPal — Stakeholder Roadmap

**Product:** AiPal is a voice-first companion. **Today** is the companion's operational memory — users talk; AiPal understands, summarizes, schedules, and nudges. Users confirm before tasks commit.

**Current release:** See `apps/mobile/pubspec.yaml` (Play Internal track).

---

## Differentiation pillars

| Pillar | Promise | Status |
|--------|---------|--------|
| Handsfree first | Hi Pal wake + natural Live conversation | C1 + C2 Android shipped |
| Brain owns Today | Concise titles, confirm-before-commit | C3a shipped |
| Proactive, not noisy | 12-min nudges with guardrails | C3b shipped |
| Memory over time | Preferences, patterns, snooze learning | C4 planned |
| Trust & warmth | Non-clinical, crisis-safe, transparent | Ongoing |

---

## Roadmap

| Phase | Milestone | Target |
|-------|-----------|--------|
| **Now** | Background wake (Android C2) + smart Today + nudges | Shipped |
| **Next** | Calendar import; sensitivity slider | Q3 |
| **Then** | Deep memory + learned routines | Q4 |
| **Later** | iOS parity; context integrations | 2027 |

---

## Stakeholder narrative

> AiPal is not another to-do app. Users speak naturally; AiPal extracts concise plans, asks once to confirm, and proactively helps before each commitment — without spam or clinical positioning.

---

## Competitive ideas (enhanced for AiPal)

1. **Event-driven companion** — Tasks and calendar events trigger brain actions without user prompt.
2. **Episodic memory** — Adapt tone and timing from past snoozes and completions.
3. **Confidence UI** — Draft cards show short title + time + expandable notes.
4. **Routine intelligence** — Learn repeated confirms as personal routines.
5. **Focus companion** — Timer + "2 min left" nudge + auto-complete offer.
6. **End-of-day closure** — Evening recap closes loops and drafts tomorrow.
7. **Explainable nudges** — User can see why AiPal spoke up.
8. **Compose-and-send drafts** — User describes a message; AiPal drafts SMS/email for review, edit, and manual copy/send (no auto-send).
9. **Privacy story** — On-device wake word; cloud LLM with clear consent.

---

## Porcupine vs OpenWakeWord (decision record)

We chose **OpenWakeWord** (vendor-independent). Commercial alternatives (~$6k/yr) were rejected for cost and lock-in. See `docs/decisions/wake-word-engine.md`.
