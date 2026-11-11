#!/usr/bin/env bash
# Start the Glass Box stack. Converts the FDA workbooks to CSV first when the
# CSVs are missing or older than their workbooks, writes LibreChat's configuration
# from agent/, then runs docker compose and creates the demo admin on first start.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env. Run 'cp .env.example .env' and fill it in." >&2
  exit 1
fi

# LibreChat's encryption and session secrets: generated once, kept in .env.
random_hex() { head -c "$1" /dev/urandom | od -An -vtx1 | tr -d ' \n'; }
for spec in CREDS_KEY:32 CREDS_IV:16 JWT_SECRET:32 JWT_REFRESH_SECRET:32; do
  name="LIBRECHAT_${spec%%:*}"
  if ! grep -q "^${name}=." .env; then
    printf '%s=%s\n' "$name" "$(random_hex "${spec##*:}")" >> .env
    echo "Generated ${name} in .env"
  fi
done

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

# LibreChat reads its configuration at startup, so write it from agent/ first, and restart a
# running LibreChat if the configuration changed.
config=librechat/librechat.yaml
before="$(cat "$config" 2>/dev/null || true)"
docker compose build --quiet jupyter
docker compose run --rm --no-deps -T jupyter python -m agent.librechat_config

docker compose up -d --wait --wait-timeout 900
if [[ -n "$before" && "$before" != "$(cat "$config")" ]]; then
  echo "LibreChat configuration changed; restarting LibreChat..."
  docker compose restart librechat
  docker compose up -d --wait --wait-timeout 300 librechat
fi

# Read the effective values from the container, so compose defaults show up too.
admin_email="$(docker compose exec -T jupyter printenv ADMIN_EMAIL)"
admin_password="$(docker compose exec -T jupyter printenv ADMIN_PASSWORD)"

# The demo admin (the first LibreChat user is its administrator). Rerunning is harmless.
users="$(docker compose exec -T librechat npm run --silent list-users 2>/dev/null || true)"
if ! grep -qF "Email: ${admin_email}" <<<"$users"; then
  # The script also prints LibreChat's whole configuration; show only its verdict.
  if output="$(docker compose exec -T librechat npm run --silent create-user -- \
      "$admin_email" "Admin" "admin" "$admin_password" --email-verified=true 2>&1)"; then
    echo "Created the LibreChat admin (${admin_email})"
  else
    echo "Warning: could not create the LibreChat admin:" >&2
    grep -i "error" <<<"$output" | tail -3 >&2
  fi
fi

echo
echo "LibreChat:   http://localhost:3080"
echo "  login:     ${admin_email}"
echo "  password:  ${admin_password}"
echo "  model:     Glass Box FDA"
echo "JupyterLab:  http://localhost:8888  (token: JUPYTER_TOKEN in .env)"
