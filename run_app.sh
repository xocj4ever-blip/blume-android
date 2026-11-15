#!/usr/bin/env bash
# 🌸 Blume Studio Mobile - Quick Launcher

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8088}"

echo "=========================================================="
echo "🌸 Starting Blume Studio (Android App Web Simulator)"
echo "   Tagline: One Language. Two Memory Models. One Unified IR."
echo "=========================================================="
echo ""
echo "📱 Open in your browser on ChromeOS / Linux:"
echo "   👉 http://localhost:${PORT}"
echo ""
echo "Press Ctrl+C to stop."
echo ""

exec python3 "$SCRIPT_DIR/simulator/server.py" "$PORT"
