#!/usr/bin/env bash
# Runs the local FastAPI service. Start frontend separately with npm --prefix frontend run dev.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${DATABASE_URL:?Set DATABASE_URL to a local Postgres connection URL first.}"
exec uv run uvicorn quantic_hr.bff:app --app-dir src --host 127.0.0.1 --port "${QUANTIC_API_PORT:-8000}"
