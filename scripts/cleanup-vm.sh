#!/usr/bin/env bash
# Conservative VM disk cleanup for AiPal. Defaults to dry-run; pass --execute to delete.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXECUTE=0
REMOVE_OLLAMA=0
TRIM_DEV_VENV=0

for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --remove-ollama) REMOVE_OLLAMA=1 ;;
    --trim-dev-venv) TRIM_DEV_VENV=1 ;;
    -h|--help)
      echo "Usage: $0 [--execute] [--remove-ollama] [--trim-dev-venv]"
      echo "  Default: dry-run only (lists targets, runs health checks, deletes nothing)"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

die() { echo "ERROR: $*" >&2; exit 1; }
log() { echo "$*"; }

DF_BEFORE="$(df -h / | tail -1 | awk '{print $3 " used, " $4 " free (" $5 ")"}')"
log "=== AiPal VM cleanup ($([[ $EXECUTE == 1 ]] && echo EXECUTE || echo DRY-RUN)) ==="
log "Disk before: $DF_BEFORE"

log ""
log "--- Pre-flight health checks ---"
systemctl is-active aipal-v2.service >/dev/null || die "aipal-v2.service not active"
curl -sf http://127.0.0.1:8102/api/v2/health >/dev/null || die "API health check failed"
docker ps --filter name=aipal-postgres --format '{{.Names}}' | grep -q aipal-postgres \
  || die "aipal-postgres container not running"
log "OK: API + Postgres healthy"

tier1_action() {
  local desc="$1"
  shift
  if [[ $EXECUTE == 1 ]]; then
    log "EXEC: $desc"
    "$@"
  else
    log "DRY-RUN: $desc"
  fi
}

log ""
log "--- Tier 1 targets (safe caches + old releases) ---"

if [[ -d "$HOME/.gradle/caches" ]]; then
  du -sh "$HOME/.gradle/caches" "$HOME/.gradle/daemon" 2>/dev/null || true
  tier1_action "remove ~/.gradle/caches and ~/.gradle/daemon" \
    rm -rf "$HOME/.gradle/caches" "$HOME/.gradle/daemon"
fi

if [[ -d "$HOME/.cache/pip" ]]; then
  du -sh "$HOME/.cache/pip" 2>/dev/null || true
  if [[ $EXECUTE == 1 ]]; then
    if [[ -x "$ROOT/apps/api/.venv/bin/pip" ]]; then
      "$ROOT/apps/api/.venv/bin/pip" cache purge || true
    else
      pip3 cache purge 2>/dev/null || true
    fi
  else
    log "DRY-RUN: pip cache purge"
  fi
fi

if [[ -d "$ROOT/apps/mobile/build" ]]; then
  du -sh "$ROOT/apps/mobile/build" 2>/dev/null || true
  tier1_action "flutter clean" bash -c "cd '$ROOT/apps/mobile' && /opt/flutter/bin/flutter clean"
fi

ARTIFACTS="$ROOT/.release_artifacts"
if [[ -d "$ARTIFACTS" ]]; then
  log "AAB artifacts in $ARTIFACTS:"
  ls -lh "$ARTIFACTS"/*.aab 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}' || true
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="$(basename "$f")"
    if [[ "$base" != *v23* && "$base" != *v22* ]]; then
      tier1_action "delete AAB $base" rm -f "$f"
    fi
  done < <(find "$ARTIFACTS" -maxdepth 1 -name 'aipal-*.aab' -type f 2>/dev/null \
    | grep -v 'v23' | grep -v 'v22' || true)
fi

DOWNLOADS="/var/www/aipal-downloads"
if [[ -d "$DOWNLOADS" ]]; then
  log "APK downloads in $DOWNLOADS:"
  ls -lh "$DOWNLOADS"/*.apk 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}' || true
  while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="$(basename "$f")"
    [[ "$base" == "aipal-latest.apk" ]] && continue
    [[ "$base" == *v23.apk ]] && continue
    [[ "$base" == *v22.apk ]] && continue
    tier1_action "delete APK $base" sudo rm -f "$f"
  done < <(find "$DOWNLOADS" -maxdepth 1 -name 'aipal-*.apk' -type f 2>/dev/null || true)
fi

tier1_action "journalctl vacuum to 200M" sudo journalctl --vacuum-size=200M

if [[ $REMOVE_OLLAMA == 1 ]]; then
  log ""
  log "--- Tier 2: Ollama (opt-in) ---"
  tier1_action "remove ollama container" docker rm -f aipal-ollama-1 2>/dev/null || true
  tier1_action "remove ollama image" docker rmi ollama/ollama:latest 2>/dev/null || true
  log "REMINDER: edit /etc/default/aipal-v2 and remove LLM_FALLBACK_PROVIDER=ollama if dropping fallback"
fi

if [[ $TRIM_DEV_VENV == 1 ]]; then
  log ""
  log "--- Tier 2: trim dev venv torch (opt-in) ---"
  VENV="$ROOT/apps/api/.venv"
  if [[ -x "$VENV/bin/pip" ]]; then
    if [[ $EXECUTE == 1 ]]; then
      "$VENV/bin/pip" freeze > "$ROOT/.venv-freeze-backup.txt" 2>/dev/null || true
      log "EXEC: pip freeze backup -> $ROOT/.venv-freeze-backup.txt"
      "$VENV/bin/pip" uninstall -y torch triton 2>/dev/null || true
      "$VENV/bin/pip" uninstall -y $(pip list 2>/dev/null | grep -i '^nvidia' | awk '{print $1}') 2>/dev/null || true
    else
      log "DRY-RUN: pip uninstall torch triton nvidia-* in dev venv"
    fi
  fi
fi

if [[ $EXECUTE == 1 ]]; then
  log ""
  log "--- Post-flight ---"
  DF_AFTER="$(df -h / | tail -1 | awk '{print $3 " used, " $4 " free (" $5 ")"}')"
  log "Disk after: $DF_AFTER"
  if [[ -x "$ROOT/apps/api/.venv/bin/pytest" ]]; then
    "$ROOT/apps/api/.venv/bin/pytest" "$ROOT/apps/api/tests/" -q
  fi
  curl -sf http://127.0.0.1:8102/api/v2/health >/dev/null && log "OK: API still healthy"
  log "Note: next flutter build may be slower (gradle cold cache)."
else
  log ""
  log "Dry-run complete. Re-run with --execute to apply Tier 1 cleanup."
fi
