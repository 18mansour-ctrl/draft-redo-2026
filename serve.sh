#!/bin/sh
set -eu
cd "$(dirname "$0")"
PORT="${1:-${PORT:-8172}}"
echo "2026 Redo on http://localhost:$PORT/"
exec python3 -m http.server "$PORT" --bind 127.0.0.1
