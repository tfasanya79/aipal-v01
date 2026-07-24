#!/usr/bin/env bash
# Build and publish v9+ to APK sideload, Flutter web, and optionally Play Internal.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE="$ROOT/apps/mobile"
SECRETS="$ROOT/.secrets"
SIGNING_ENV="$SECRETS/android-signing.env"
API_BASE_URL="${API_BASE_URL:-https://43.160.220.9.sslip.io/api/v2}"
DOWNLOADS_ROOT="/var/www/aipal-downloads"
WEB_ROOT="/var/www/aipal-v2-web"
UPLOAD_PLAY="${UPLOAD_PLAY:-0}"

prune_release_files() {
  local version_code="$1"
  local prev_code="$2"
  local artifacts="$ROOT/.release_artifacts"
  if [[ -d "$artifacts" ]]; then
    find "$artifacts" -maxdepth 1 -name 'aipal-*.aab' -type f 2>/dev/null | while read -r f; do
      local base
      base="$(basename "$f")"
      [[ "$base" == *"v${version_code}"* ]] && continue
      [[ "$base" == *"v${prev_code}"* ]] && continue
      rm -f "$f"
    done
  fi
  if [[ -d "$DOWNLOADS_ROOT" ]]; then
    find "$DOWNLOADS_ROOT" -maxdepth 1 -name 'aipal-v*.apk' -type f 2>/dev/null | while read -r f; do
      local base
      base="$(basename "$f")"
      [[ "$base" == "aipal-latest.apk" ]] && continue
      [[ "$base" == *"v${version_code}.apk" ]] && continue
      [[ "$base" == *"v${prev_code}.apk" ]] && continue
      sudo rm -f "$f"
    done
  fi
}

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="/opt/flutter/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/usr/local/bin:${PATH}"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$SIGNING_ENV" ]] || die "Missing $SIGNING_ENV"
# shellcheck source=/dev/null
source "$SIGNING_ENV"

command -v flutter >/dev/null || die "Flutter SDK not on PATH"

chmod +x "$ROOT/scripts/check-brand-copy.sh" "$ROOT/scripts/generate_aipal_icons.py" 2>/dev/null || true
chmod +x "$ROOT/scripts/build-status-page.sh" "$ROOT/scripts/setup-status-auth.sh" 2>/dev/null || true
"$ROOT/scripts/check-brand-copy.sh"
if [[ -f "$ROOT/apps/api/.venv/bin/python" ]]; then
  "$ROOT/apps/api/.venv/bin/python" -m pytest "$ROOT/apps/api/tests/" -q || die "pytest failed"
elif command -v python3 >/dev/null; then
  (cd "$ROOT/apps/api" && python3 -m pytest tests/ -q) || die "pytest failed"
fi

# Deploy the API to the production path and restart the service BEFORE smoke
# testing, so smoke validates the freshly deployed server (not stale code).
# Without this, mobile/web ship while the API silently stays on old code.
API_DEPLOY_PATH="${API_DEPLOY_PATH:-/opt/aipal-v2}"
API_SERVICE="${API_SERVICE:-aipal-v2.service}"
SKIP_API_DEPLOY="${SKIP_API_DEPLOY:-0}"
if [[ "$SKIP_API_DEPLOY" != "1" && -d "$API_DEPLOY_PATH" ]]; then
  echo "Deploying API to $API_DEPLOY_PATH and restarting $API_SERVICE..."
  sudo rsync -a --delete \
    --exclude=.venv --exclude=__pycache__ --exclude='.env' \
    "$ROOT/apps/api/" "$API_DEPLOY_PATH/apps/api/" || die "API rsync failed"
  sudo systemctl restart "$API_SERVICE" || die "API service restart failed"
  for _i in $(seq 1 20); do
    curl -sf "http://127.0.0.1:8102/api/v2/health" -o /dev/null && break
    sleep 0.5
    [[ "$_i" == "20" ]] && die "API health check failed after restart"
  done
  echo "API deployed and healthy."
fi

chmod +x "$ROOT/scripts/smoke-test.sh"
"$ROOT/scripts/smoke-test.sh" || die "smoke-test failed (is aipal-v2.service running?)"
python3 "$ROOT/scripts/generate_aipal_icons.py"
"$ROOT/scripts/build-status-page.sh"
STATUS_ROOT="/var/www/aipal-status"
sudo mkdir -p "$STATUS_ROOT"
sudo cp "$ROOT/infra/status/out/index.html" "$STATUS_ROOT/index.html"
"$ROOT/scripts/setup-status-auth.sh" || true

cd "$MOBILE"
flutter pub get
flutter test || die "flutter test failed"
flutter build apk --release --dart-define="API_BASE_URL=$API_BASE_URL"
flutter build web --release --base-href /app/ --dart-define="API_BASE_URL=$API_BASE_URL"

VERSION_LINE="$(grep '^version:' pubspec.yaml | awk '{print $2}')"
VERSION_NAME="${VERSION_LINE%%+*}"
VERSION_CODE="${VERSION_LINE##*+}"
APK_SRC="build/app/outputs/flutter-apk/app-release.apk"
APK_NAME="aipal-v${VERSION_NAME}-v${VERSION_CODE}.apk"
SHA256="$(sha256sum "$APK_SRC" | awk '{print $1}')"

sudo mkdir -p "$DOWNLOADS_ROOT" "$WEB_ROOT"
sudo cp "$APK_SRC" "$DOWNLOADS_ROOT/aipal-latest.apk"
sudo cp "$APK_SRC" "$DOWNLOADS_ROOT/$APK_NAME"
prune_release_files "$VERSION_CODE" "$((VERSION_CODE - 1))"
sudo rsync -a --delete "$MOBILE/build/web/" "$WEB_ROOT/"

INDEX_SRC="$ROOT/infra/downloads/index.html"
if [[ -f "$INDEX_SRC" ]]; then
  sed -e "s/build 9/build ${VERSION_CODE}/g" \
      -e "s/2.0.0 (build ${VERSION_CODE})/${VERSION_NAME} (build ${VERSION_CODE})/g" \
      -e "s/aipal-v2.0.0-v9.apk/${APK_NAME}/g" \
      -e "s/(computed on deploy)/${SHA256}/" \
      "$INDEX_SRC" | sudo tee "$DOWNLOADS_ROOT/index.html" >/dev/null
fi

sudo chown -R www-data:www-data "$DOWNLOADS_ROOT" 2>/dev/null || sudo chown -R caddy:caddy "$DOWNLOADS_ROOT" 2>/dev/null || true
sudo chown -R www-data:www-data "$WEB_ROOT" 2>/dev/null || sudo chown -R caddy:caddy "$WEB_ROOT" 2>/dev/null || true

CADDYFILE="$ROOT/infra/caddy/Caddyfile"
if [[ -f "$CADDYFILE" ]] && command -v caddy >/dev/null; then
  sudo cp "$CADDYFILE" /etc/caddy/Caddyfile 2>/dev/null || true
  if [[ -f /etc/caddy/status-auth.env ]]; then
    sudo systemctl daemon-reload 2>/dev/null || true
    sudo systemctl restart caddy 2>/dev/null || sudo systemctl reload caddy 2>/dev/null || true
  else
    sudo systemctl reload caddy 2>/dev/null || true
  fi
fi

if [[ "$UPLOAD_PLAY" == "1" ]]; then
  "$ROOT/scripts/deploy-android-internal.sh"
fi

echo ""
echo "=== Deploy complete ==="
echo "versionName=$VERSION_NAME versionCode=$VERSION_CODE"
echo "SHA-256=$SHA256"
echo ""
echo "APK sideload:"
echo "  https://43.160.220.9.sslip.io/downloads/"
echo "  https://43.160.220.9.sslip.io/downloads/aipal-latest.apk"
echo ""
echo "Web app:"
echo "  https://43.160.220.9.sslip.io/app/"
echo ""
echo "Stakeholder status (password in .secrets/status-page-credentials.txt):"
echo "  https://43.160.220.9.sslip.io/status/"
echo ""
echo "If install fails: uninstall Play Store AiPal first (signature conflict)."
if [[ "$UPLOAD_PLAY" != "1" ]]; then
  echo "Play Internal: run UPLOAD_PLAY=1 $0 to upload AAB"
fi
