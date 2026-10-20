#!/usr/bin/env bash
# Start a project-local Homebrew Postgres on port 5433. No AWS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGDATA="${PGDATA:-$ROOT/.local/pgdata}"
PGPORT="${PGPORT:-5433}"
PGUSER="${PGUSER:-quantic}"
PGDATABASE="${PGDATABASE:-quantic_hr}"
LOG="$ROOT/.local/postgres.log"
export PGHOST=127.0.0.1
export PGPORT PGUSER PGDATABASE

mkdir -p "$ROOT/.local"

if ! command -v initdb >/dev/null || ! command -v pg_ctl >/dev/null; then
  echo "ERROR: PostgreSQL client/server tools are required (Homebrew postgresql)."
  exit 1
fi

start_db() {
  if [[ ! -d "$PGDATA" ]]; then
    initdb -D "$PGDATA" -U "$PGUSER" -A trust --locale=C --encoding=UTF8 >/dev/null
  fi
  if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    echo "Postgres already running on port $PGPORT"
  else
    pg_ctl -D "$PGDATA" -l "$LOG" -o "-p $PGPORT -k $ROOT/.local" start >/dev/null
    echo "Started project-local Postgres on $PGPORT"
  fi
  if ! psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'" | grep -q 1; then
    createdb -U "$PGUSER" "$PGDATABASE"
  fi
  DATABASE_URL="postgresql://${PGUSER}@127.0.0.1:${PGPORT}/${PGDATABASE}" \
    python3 "$ROOT/scripts/apply_local_schema.py" || \
    DATABASE_URL="postgresql://${PGUSER}@127.0.0.1:${PGPORT}/${PGDATABASE}" \
    "$ROOT/.venv/bin/python" "$ROOT/scripts/apply_local_schema.py"
  echo "Local database $PGDATABASE is ready (postgresql://$PGUSER@127.0.0.1:$PGPORT/$PGDATABASE)"
}

stop_db() {
  if pg_ctl -D "$PGDATA" status >/dev/null 2>&1; then
    pg_ctl -D "$PGDATA" stop >/dev/null
    echo "Stopped project-local Postgres"
  fi
}

case "${1:-start}" in
  start) start_db ;;
  stop) stop_db ;;
  reset) stop_db; rm -rf "$PGDATA"; start_db ;;
  *) echo "Usage: $0 start|stop|reset"; exit 1 ;;
esac
