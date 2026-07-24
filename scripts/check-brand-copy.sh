#!/usr/bin/env bash
# Fail if forbidden third-party names or wrong AiPal casing appear in shipped surfaces.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FAIL=0

check_forbidden() {
  local pattern="$1"
  local label="$2"
  if rg -i "$pattern" \
    "$ROOT/apps/mobile/lib" \
    "$ROOT/apps/mobile/web" \
    "$ROOT/apps/api/app" \
    --glob '!**/__pycache__/**' 2>/dev/null; then
    echo "FAIL: found forbidden $label"
    FAIL=1
  fi
}

check_wrong_name() {
  local pattern="$1"
  if rg "$pattern" \
    "$ROOT/apps/mobile/lib" \
    "$ROOT/apps/mobile/web/index.html" \
    "$ROOT/apps/mobile/web/manifest.json" \
    "$ROOT/apps/mobile/android/app/src/main/AndroidManifest.xml" \
    2>/dev/null; then
    echo "FAIL: wrong app name variant ($pattern) — use AiPal"
    FAIL=1
  fi
}

# Third-party planner app (blocked terms — add variants without naming in output messages)
FORBIDDEN='tiimo|tii\s*mo'
if rg -i "$FORBIDDEN" \
  "$ROOT/apps/mobile/lib" \
  "$ROOT/apps/mobile/web" \
  "$ROOT/apps/api/app" 2>/dev/null; then
  echo "FAIL: forbidden third-party reference in shipped surfaces"
  FAIL=1
fi

check_wrong_name 'AIpal'
check_wrong_name 'AIPAL'
check_wrong_name '"aipal"'
check_wrong_name "'aipal'"

# Voice UX: LLM/greetings must not push hold/tap/press-to-talk (orb UI copy is separate)
PTT_PATTERN='hold to talk|press to talk|tap to talk'
if rg -i "$PTT_PATTERN" \
  "$ROOT/apps/api/app/llm_provider.py" \
  "$ROOT/apps/api/app/companion_prompts.py" \
  "$ROOT/apps/api/app/routers/daily.py" 2>/dev/null; then
  echo "FAIL: push-to-talk phrasing in API voice copy — user is already in Live/text"
  FAIL=1
fi

if [[ $FAIL -ne 0 ]]; then
  exit 1
fi
echo "Brand copy check passed."
