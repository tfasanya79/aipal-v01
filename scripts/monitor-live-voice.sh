#!/usr/bin/env bash
# Tail Live Voice v2 conversation logs from the API service (run on the VM).
# Usage: ./scripts/monitor-live-voice.sh
set -euo pipefail

echo "Monitoring Live Voice logs (Ctrl+C to stop)…"
echo "Look for: session_started, speech_start, speech_end, transcript, turn_complete"
echo ""

sudo journalctl -u aipal-v2.service -f --no-pager 2>&1 \
  | grep --line-buffered -iE 'live_voice|aipal\.ws|whisper|transcript|speech_|turn_complete|error|exception'
