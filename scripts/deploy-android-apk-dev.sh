#!/usr/bin/env bash
# Build signed release APK and publish to /var/www/aipal-downloads for sideload testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE="$ROOT/apps/mobile"
SECRETS="$ROOT/.secrets"
SIGNING_ENV="$SECRETS/android-signing.env"
API_BASE_URL="${API_BASE_URL:-https://43.160.220.9.sslip.io/api/v2}"
WEB_ROOT="/var/www/aipal-downloads"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="/opt/flutter/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/usr/local/bin:${PATH}"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$SIGNING_ENV" ]] || die "Missing $SIGNING_ENV"
# shellcheck source=/dev/null
source "$SIGNING_ENV"

command -v flutter >/dev/null || die "Flutter SDK not on PATH"

cd "$MOBILE"
flutter pub get
flutter build apk --release --dart-define="API_BASE_URL=$API_BASE_URL"

VERSION_LINE="$(grep '^version:' pubspec.yaml | awk '{print $2}')"
VERSION_NAME="${VERSION_LINE%%+*}"
VERSION_CODE="${VERSION_LINE##*+}"
APK_SRC="build/app/outputs/flutter-apk/app-release.apk"
APK_NAME="aipal-v${VERSION_NAME}-v${VERSION_CODE}.apk"
SHA256="$(sha256sum "$APK_SRC" | awk '{print $1}')"

sudo mkdir -p "$WEB_ROOT"
sudo cp "$APK_SRC" "$WEB_ROOT/aipal-latest.apk"
sudo cp "$APK_SRC" "$WEB_ROOT/$APK_NAME"
sudo chown -R www-data:www-data "$WEB_ROOT" 2>/dev/null || sudo chown -R caddy:caddy "$WEB_ROOT" 2>/dev/null || true

echo "Built: $APK_SRC"
echo "Published:"
echo "  https://43.160.220.9.sslip.io/downloads/aipal-latest.apk"
echo "  https://43.160.220.9.sslip.io/downloads/$APK_NAME"
echo "versionName=$VERSION_NAME versionCode=$VERSION_CODE"
echo "SHA-256=$SHA256"
