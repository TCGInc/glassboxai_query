#!/usr/bin/env bash
set -euo pipefail

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=agent_ro_user="$AGENT_RO_USER" <<'SQL'
GRANT USAGE ON SCHEMA fda TO :"agent_ro_user";
GRANT SELECT ON ALL TABLES IN SCHEMA fda TO :"agent_ro_user";
ALTER DEFAULT PRIVILEGES IN SCHEMA fda
  GRANT SELECT ON TABLES TO :"agent_ro_user";
SQL
