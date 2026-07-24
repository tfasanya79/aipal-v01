#!/usr/bin/env bash
# AiPal API smoke tests — run before deploy or via release-qa-agent.
set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:8102/api/v2}"
EMAIL="smoke-$(date +%s)@example.com"

die() { echo "SMOKE FAIL: $*" >&2; exit 1; }

echo "Smoke: health"
curl -sf "$API_BASE/health" -o /dev/null || die "health unreachable"

echo "Smoke: auth"
REG=$(curl -sf -X POST "$API_BASE/auth/register" -H 'Content-Type: application/json' -d "{\"email\":\"$EMAIL\"}")
DEV=$(echo "$REG" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dev_token',''))")
[[ -n "$DEV" ]] || die "no dev_token"
VERIFY=$(curl -sf -X POST "$API_BASE/auth/verify" -H 'Content-Type: application/json' -d "{\"token\":\"$DEV\"}")
TOKEN=$(echo "$VERIFY" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
AUTH="Authorization: Bearer $TOKEN"

echo "Smoke: today-view"
curl -sf "$API_BASE/tasks/today-view" -H "$AUTH" -o /dev/null || die "today-view"

echo "Smoke: text turn + session"
SESSION="smoke-session-$$"
TURN=$(curl -sf -X POST "$API_BASE/turn/text" -H "$AUTH" -H 'Content-Type: application/json' \
  -d "{\"text\":\"meeting by 4pm and swimming by 6pm\",\"session_id\":\"$SESSION\"}")
echo "$TURN" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('reply'); print('  reply ok, session', d.get('session_id'))"

echo "Smoke: plan-draft"
DRAFT=$(curl -sf "$API_BASE/tasks/plan-draft" -H "$AUTH" || echo "null")
if echo "$DRAFT" | grep -q proposed_tasks; then
  curl -sf -X POST "$API_BASE/tasks/plan-draft/confirm" -H "$AUTH" -o /dev/null || die "confirm"
  echo "  plan confirmed"
else
  echo "  no draft (LLM may be offline — ok for smoke)"
fi

echo "SMOKE PASS"
