#!/usr/bin/env bash
# Start the Glass Box stack. Converts the FDA workbooks to CSV first when the
# CSVs are missing or older than their workbooks, then runs docker compose.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run 'cp .env.example .env' and fill it in." >&2
  exit 1
fi

needs_convert=0
for name in fda_inspections fda_citations fda_recall_events; do
  if [[ data/raw/$name.xlsx -nt data/$name.csv ]]; then
    needs_convert=1
  fi
done

if (( needs_convert )); then
  echo "Converting FDA workbooks to CSV (about a minute)..."
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD":/work -w /work \
    python:3.12-slim sh -c \
    'pip install -q --disable-pip-version-check --user -r requirements-import.txt && python scripts/convert_fda_workbooks.py'
  echo "If the database volume already exists, run './stop.sh --reset' first to reload it."
fi

export HOST_UID="$(id -u)" HOST_GID="$(id -g)"
docker compose up -d --build --wait --wait-timeout 900

# Configure Open WebUI from agent/ (idempotent). A failure here should not hide that the stack is up.
docker compose exec -T jupyter python -m agent.openwebui_provision \
  || echo "Warning: Open WebUI was not configured; rerun: docker compose exec jupyter python -m agent.openwebui_provision" >&2

echo
echo "JupyterLab: http://localhost:8888  (token: JUPYTER_TOKEN in .env)"
echo "Open WebUI: http://localhost:3000  (login: WEBUI_ADMIN_EMAIL / WEBUI_ADMIN_PASSWORD in .env; model \"Glass Box FDA\")"
