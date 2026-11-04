#!/usr/bin/env bash
# Runs the FastAPI service. Requires DATABASE_URL pointing at Aurora and AWS creds for Bedrock.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
: "${DATABASE_URL:?Set DATABASE_URL to the Aurora connection URL first.}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
exec uv run uvicorn quantic_hr.bff:app --app-dir src --host 127.0.0.1 --port "${QUANTIC_API_PORT:-8000}"
