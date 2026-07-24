#!/usr/bin/env bash
# Build signed release AAB and upload to Google Play Internal testing track.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MOBILE="$ROOT/apps/mobile"

# VM toolchain (login shells may have these via .bashrc; scripts do not)
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/android-sdk}"
export ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-$ANDROID_HOME}"
export PATH="/opt/flutter/bin:/opt/android-sdk/cmdline-tools/latest/bin:/opt/android-sdk/platform-tools:/usr/local/bin:${PATH}"
SECRETS="$ROOT/.secrets"
SIGNING_ENV="$SECRETS/android-signing.env"
PLAY_JSON="$SECRETS/play-api.json"
API_BASE_URL="${API_BASE_URL:-https://43.160.220.9.sslip.io/api/v2}"
ARTIFACTS="$ROOT/.release_artifacts"

die() { echo "ERROR: $*" >&2; exit 1; }

[[ -f "$SIGNING_ENV" ]] || die "Missing $SIGNING_ENV"
# shellcheck source=/dev/null
source "$SIGNING_ENV"

[[ -f "$PLAY_JSON" ]] || die "Missing $PLAY_JSON — scp your Play API JSON to the VM first"

EXPECTED_EMAIL="aipal-play-uploader@innovativeinventors.iam.gserviceaccount.com"
ACTUAL_EMAIL="$(python3 -c "import json; print(json.load(open('$PLAY_JSON'))['client_email'])")"
[[ "$ACTUAL_EMAIL" == "$EXPECTED_EMAIL" ]] || die "play-api.json client_email mismatch: got $ACTUAL_EMAIL"

chmod 700 "$SECRETS"
chmod 600 "$PLAY_JSON"

command -v flutter >/dev/null || die "Flutter SDK not on PATH (expected /opt/flutter/bin)"
command -v fastlane >/dev/null || die "fastlane not installed"

cd "$MOBILE"
flutter pub get
flutter build appbundle --release --dart-define="API_BASE_URL=$API_BASE_URL"

VERSION_LINE="$(grep '^version:' pubspec.yaml | awk '{print $2}')"
VERSION_NAME="${VERSION_LINE%%+*}"
VERSION_CODE="${VERSION_LINE##*+}"
DATE="$(date +%Y%m%d)"
AAB_SRC="build/app/outputs/bundle/release/app-release.aab"
AAB_NAME="aipal-v${VERSION_NAME}-v${VERSION_CODE}-${DATE}.aab"
AAB_PATH="$ARTIFACTS/$AAB_NAME"

mkdir -p "$ARTIFACTS"
cp "$AAB_SRC" "$AAB_PATH"
SHA256="$(sha256sum "$AAB_PATH" | awk '{print $1}')"

echo "Built: $AAB_PATH"
echo "versionName=$VERSION_NAME versionCode=$VERSION_CODE"
echo "SHA-256=$SHA256"

cd "$MOBILE"
AAB_PATH="$AAB_PATH" fastlane android upload_internal "aab:$AAB_PATH"

echo ""
echo "Upload complete → Play Internal track"
echo "  Package: io.aipal.mvp"
echo "  versionName: $VERSION_NAME"
echo "  versionCode: $VERSION_CODE"
echo "  SHA-256: $SHA256"
echo "  AAB: $AAB_PATH"
