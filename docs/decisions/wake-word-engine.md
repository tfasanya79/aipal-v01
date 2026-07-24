# Wake word engine decision — OpenWakeWord vs Porcupine

**Status:** Accepted — OpenWakeWord, wake phrase **"Hi Pal"** (C1 foreground + C2 Android background)  
**Date:** 2026-06-11  
**Shipped phrase:** "Hi Pal" only

## Context

AiPal's north star is hands-free voice: user says a wake phrase, companion listens, VAD turn-taking handles the rest. Phase C (post brain + Today polish) adds always-on or foreground wake. This doc compares the two leading options given a **preference for vendor independence** and Flutter mobile targets.

## Comparison

| Dimension | OpenWakeWord | Picovoice Porcupine |
|-----------|--------------|---------------------|
| **License** | Code: **Apache 2.0**. Bundled pre-trained models: **CC BY-NC-SA 4.0** (non-commercial). Custom models via [openwakeword.com](https://openwakeword.com/) can be self-hosted ONNX. | **Commercial** product. Free tier: personal / non-commercial only (~1 MAU). Commercial from ~$6k/yr (Foundation) or enterprise quote. SDK wrappers partially open; engine is proprietary. |
| **Offline inference** | Yes — ONNX/TFLite on-device after model download. No cloud at runtime. | Yes — `.ppn` models run on-device. Periodic **AccessKey** validation / usage reporting needs network. |
| **Flutter integration** | **No official plugin.** Requires porting a 3-stage pipeline (melspectrogram → embedding → wake model) via ONNX Runtime or TFLite + platform channels. Maintainer confirms feasible but non-trivial ([discussion #177](https://github.com/dscripka/openWakeWord/discussions/177)). | **Official `porcupine_flutter`** package. Train keyword in Console → drop `.ppn` per platform. Production-ready path in days. |
| **Custom wake phrases** | Train "Hi Pal" / "Hey AiPal" via openWakeWord trainer or openwakeword.com → ONNX. Full control over model artifacts. | Type-to-train in Picovoice Console in seconds. Branded phrases supported; models are platform-specific `.ppn` files. |
| **Battery / CPU** | Small models (~100KB class); continuous listening cost depends on implementation quality. No published Flutter benchmarks — engineering risk. | Optimized for mobile; documented low CPU wake loop. Industry default for production wake on phones. |
| **Accuracy** | Good on trained phrases; quality depends on training data and phrase design. Community reports solid results on Pi/HA; mobile Flutter path unproven for AiPal phrases. | High accuracy, tuned for keyword spotting; Console validates phrase quality. |
| **Maintenance burden** | **High** for Flutter: own the audio pipeline, model updates, per-platform ONNX builds, false-positive tuning. **Low** if staying Python/server-side only (not our mobile path). | **Low** for integration; **medium** for licensing/compliance and AccessKey ops. |
| **Vendor dependency** | **Low** — open code, exportable ONNX, no runtime license server. Model license is the main constraint for bundled pre-trained assets (use custom commercial-friendly models for prod). | **High** — AccessKey, terms changes, MAU caps, revocable license, commercial pricing for shipped product. |

## Decision (accepted)

**Engine: OpenWakeWord** via Flutter FFI package [`open_wake_word`](https://pub.dev/packages/open_wake_word) (ONNX Runtime native). Custom `hi_pal_v0.1.onnx` trained with the openWakeWord toolchain (`scripts/train-hi-pal-wakeword.py`).

**Rejected: Picovoice Porcupine** — commercial ~$6k/yr Foundation tier, AccessKey dependency, and vendor lock-in conflict with AiPal's independence goal. Porcupine is **not** in shipped code.

**C1 scope (shipped v2.2.0+15):** Foreground wake when user opts in ("Listen for Hi Pal" in Settings, default off). Wake → `AppState.toggleLive()`. Web shows educational copy only (no always-on mic).

**C2 scope (shipped v2.4.0+18, Android only):** `flutter_foreground_task` foreground microphone service with ongoing notification. Listen across tabs and when app is backgrounded (screen on). iOS: foreground-only on Companion tab (Apple policy). Wake → `launchApp()` + `toggleLive()`.

## Phased rollout (C1 / C2)

Naming here is **product Phase C**, not plan Phase B (brain/Today).

| Sub-phase | Scope | Platform notes |
|-----------|--------|----------------|
| **C1 — Foreground wake** | Wake word starts or resumes **Live** while app is open (Companion tab). Mic already authorized. Fallback: tap orb (existing). | Flutter plugin or native module. Web: defer (no reliable always-on mic). |
| **C2 — Background service (Android)** | **Shipped.** Foreground `Service` (microphone type) + notification; wake → open app + Live. | Android only. iOS: foreground Companion tab + Siri Shortcuts later. |
| **C3+ (out of scope here)** | Proactive nudges, richer mem0 in every turn, calendar import. | Depends on C1/C2 learnings. |

## Decision log

| Date | Decision |
|------|----------|
| 2026-06-11 | Document only. Lean OpenWakeWord; Porcupine reserved as fallback. |
| 2026-06-11 | **Accepted OpenWakeWord + "Hi Pal".** Porcupine rejected (~$6k/yr, vendor dependency). C1 shipped in mobile 2.2.0+15. |
| 2026-06-12 | **C2 Android background wake shipped** in mobile 2.4.0+18 (`WakeForegroundHandler` + `WakeBackgroundService`). |

## References

- [openWakeWord GitHub](https://github.com/dscripka/openWakeWord) (Apache 2.0)
- [OpenWakeWord Flutter discussion #177](https://github.com/dscripka/openWakeWord/discussions/177)
- [Picovoice Porcupine docs](https://picovoice.ai/docs/porcupine/)
- [porcupine_flutter tutorial](https://picovoice.ai/blog/wake-word-detection-in-flutter/)
