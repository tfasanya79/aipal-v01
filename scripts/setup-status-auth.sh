#!/usr/bin/env bash
# First-time (or rotate) stakeholder basic-auth for /status/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS="$ROOT/.secrets"
CREDS_FILE="$SECRETS/status-page-credentials.txt"
CADDY_ENV="/etc/caddy/status-auth.env"
USER_NAME="${STATUS_AUTH_USER:-stakeholder}"

die() { echo "ERROR: $*" >&2; exit 1; }

command -v caddy >/dev/null || die "caddy not installed"

mkdir -p "$SECRETS"
chmod 700 "$SECRETS"

if [[ -f "$CREDS_FILE" && -f "$CADDY_ENV" ]]; then
  echo "Status auth already configured ($CREDS_FILE). Skipping generation."
  exit 0
fi

PASSWORD="$(openssl rand -base64 18 | tr -d '/+=' | head -c 20)"
HASH="$(caddy hash-password --plaintext "$PASSWORD")"

sudo tee "$CADDY_ENV" >/dev/null <<EOF
STATUS_AUTH_USER=$USER_NAME
STATUS_AUTH_HASH=$HASH
EOF
sudo chmod 600 "$CADDY_ENV"

cat >"$CREDS_FILE" <<EOF
# AiPal stakeholder status page — share out-of-band only
URL=https://43.160.220.9.sslip.io/status/
USERNAME=$USER_NAME
PASSWORD=$PASSWORD
GENERATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
chmod 600 "$CREDS_FILE"

DROP_IN_DIR="/etc/systemd/system/caddy.service.d"
if [[ ! -f "$DROP_IN_DIR/status-auth.conf" ]]; then
  sudo mkdir -p "$DROP_IN_DIR"
  sudo tee "$DROP_IN_DIR/status-auth.conf" >/dev/null <<'EOF'
[Service]
EnvironmentFile=/etc/caddy/status-auth.env
EOF
  sudo systemctl daemon-reload
fi

echo "Status auth created. Credentials: $CREDS_FILE"
