#!/usr/bin/env bash
# Guarded SQL migration executor for Quantic Aurora via HTTPS RDS Data API.
# No SSM host, psql tunnel, NAT gateway or public PostgreSQL port needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$#" -lt 1 ]]; then
  echo "Usage: bash infrastructure/database/scripts/run-sql.sh [--check] path/to/migration.sql"
  echo "For execution set QUANTIC_ALLOW_SQL_MIGRATIONS=yes; credentials use AWS SSO profile."
  exit 2
fi

exec python3 "$SCRIPT_DIR/data_api_migrate.py" "$@"
