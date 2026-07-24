#!/usr/bin/env bash
# Bootstrap AiPal Roadmap (repository-owned project) via sync_github_project.py.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export GITHUB_TOKEN="${GITHUB_TOKEN:?GITHUB_TOKEN required}"
export GITHUB_REPOSITORY="${GITHUB_REPOSITORY:-tfasanya79/aipal}"

python3 scripts/sync_github_project.py --bootstrap "$@"
