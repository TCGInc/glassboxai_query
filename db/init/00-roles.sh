#!/usr/bin/env bash
set -euo pipefail

: "${AGENT_RO_USER:?AGENT_RO_USER must be set}"
: "${AGENT_RO_PASSWORD:?AGENT_RO_PASSWORD must be set}"

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=agent_ro_user="$AGENT_RO_USER" \
  --set=agent_ro_password="$AGENT_RO_PASSWORD" \
  --set=database_name="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"agent_ro_user"
  WITH LOGIN PASSWORD :'agent_ro_password'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;

ALTER ROLE :"agent_ro_user" SET default_transaction_read_only = on;
ALTER ROLE :"agent_ro_user" SET statement_timeout = '30s';
ALTER ROLE :"agent_ro_user" SET lock_timeout = '10s';
ALTER ROLE :"agent_ro_user" SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE :"agent_ro_user" SET search_path = fda, public;

GRANT CONNECT ON DATABASE :"database_name" TO :"agent_ro_user";
SQL
