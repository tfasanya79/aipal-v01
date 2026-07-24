# Play Internal — AiPal

**Current version:** see `apps/mobile/pubspec.yaml` (canonical).

## Build & upload

```bash
./scripts/deploy-android-internal.sh
```

Or full pipeline with Play:

```bash
UPLOAD_PLAY=1 ./scripts/deploy-all.sh
```

## Metadata

| Field | Value |
|-------|-------|
| Package | `io.aipal.mvp` |
| Target SDK | 35 |
| Track | Internal testing |

## API dependency

Mobile expects `https://43.160.220.9.sslip.io/api/v2`.
