#!/usr/bin/env bash
# Create ONLY the empty Quantic database on an already running, approved Aurora PostgreSQL cluster.
# No schema, users, extension, cluster starts, snapshots or AWS changes are performed here.
set -euo pipefail
if [[ "${QUANTIC_ALLOW_DB_CREATE:-}" != "yes" ]]; then
  echo "BLOCKED: Set QUANTIC_ALLOW_DB_CREATE=yes only after approving this database creation."
  exit 1
fi
: "${AURORA_ADMIN_DATABASE_URL:?Set AURORA_ADMIN_DATABASE_URL (admin connection to existing Café cluster, postgres database).}"
command -v psql >/dev/null || { echo "psql is required"; exit 1; }
echo "Target: existing cluster only. Database: quantic_hr. No tables or extensions."
# Connect using explicit secure Postgres URL; do not echo secrets.
if [[ "$(psql "$AURORA_ADMIN_DATABASE_URL" -X -A -t -v ON_ERROR_STOP=1 -c "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname='quantic_hr')")" == "t" ]]; then
  echo "quantic_hr already exists; no change."
  exit 0
fi
read -r -p "Type CREATE quantic_hr to create one EMPTY database: " confirmation
if [[ "$confirmation" != "CREATE quantic_hr" ]]; then echo "Cancelled."; exit 1; fi
psql "$AURORA_ADMIN_DATABASE_URL" -X -v ON_ERROR_STOP=1 -c 'CREATE DATABASE quantic_hr'
echo "Created empty quantic_hr database. No HR schema or extension was applied."
