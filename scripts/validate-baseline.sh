#!/usr/bin/env bash
# Run offline baseline checks; never deploy or contact AWS.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo "== Python / API / MCP tests =="
if ! command -v uv >/dev/null 2>&1; then echo "ERROR: uv is required"; exit 1; fi
uv sync --group dev
echo "Prerequisite: local PostgreSQL must be running and DATABASE_URL configured."
uv run pytest -q
echo "== React / Vite =="
(cd frontend && npm ci && npm run build)
echo "== CDK compilation / tests / synth (NO AWS) =="
(cd infrastructure && npm ci && npm run build && npm test -- --runInBand && npm run synth && npm run synth:reuse)
echo "PASS: offline checks. Bedrock/AgentCore/Aurora deployment NOT validated."
