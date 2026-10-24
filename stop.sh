#!/usr/bin/env bash
# Stop the Glass Box stack. With --reset, also delete the database volume so
# the next ./start.sh reloads it from the CSVs. Open WebUI state in
# openwebui/data/ is a bind mount and is not touched.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-}" in
  "")      docker compose down ;;
  --reset) docker compose down -v ;;
  *)       echo "Usage: $0 [--reset]" >&2; exit 2 ;;
esac
