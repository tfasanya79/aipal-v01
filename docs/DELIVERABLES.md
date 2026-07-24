# Deliverables tracker (moved)

**Canonical source:** [`/home/dev/docs/DELIVERABLES.md`](/home/dev/docs/DELIVERABLES.md)

The master deliverables audit, phase status, and release history live in the **docs hub** at `/home/dev/docs/`. This repo keeps:

- [`PRODUCT.md`](PRODUCT.md) — living phase checklist and acceptance criteria
- [`docs/decisions/`](decisions/) — ADRs (Live Voice v2, wake word)
- [`docs/architecture/live-voice-protocol.md`](architecture/live-voice-protocol.md) — WS protocol spec

**Current app version:** see [`apps/mobile/pubspec.yaml`](../apps/mobile/pubspec.yaml).

**CI:** Mobile workflow runs `flutter analyze` and `flutter test` (failures block CI). API: `pytest` in `deploy-all.sh`.
