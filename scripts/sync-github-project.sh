#!/usr/bin/env bash
# Sync docs/PRODUCT.md backlog to GitHub Project (AiPal Roadmap).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -z "${GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    export GITHUB_TOKEN="$(gh auth token)"
  fi
fi
exec python3 "$ROOT/scripts/sync_github_project.py" "$@"
