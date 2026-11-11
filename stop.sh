#!/usr/bin/env bash
# Stop the Glass Box stack. With --reset, also delete the volumes: the FDA
# database (the next ./start.sh reloads it from the CSVs) and LibreChat's
# database (users and chats; start.sh recreates the admin).
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  "")      docker compose down ;;
  --reset) docker compose down -v ;;
  *)       echo "Usage: $0 [--reset]" >&2; exit 2 ;;
esac
