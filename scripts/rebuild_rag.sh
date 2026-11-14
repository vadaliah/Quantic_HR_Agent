#!/usr/bin/env bash
# Rebuild the RAG index from corpus/, end to end.
#
#   scripts/rebuild_rag.sh              # full refresh: truncate, re-embed, verify
#   scripts/rebuild_rag.sh --dry-run    # parse and verify only; no AWS, no database
#   scripts/rebuild_rag.sh --keep-embeddings
#
# Needs the ADMIN database user and working AWS credentials for Titan. The
# deployed app reads through the RDS Data API with a read-only role, so this
# runs from a machine that can reach the cluster, not from the Render container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

MODE="refresh"
EXTRA=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry run"; EXTRA+=(--dry-run) ;;
    *)         EXTRA+=("$arg") ;;
  esac
done

echo "RAG rebuild"
echo "       repo root:  $REPO_ROOT"
echo "       corpus:     ${CORPUS_DIR:-corpus}"
echo "       mode:       $MODE"
echo

if [[ "$MODE" != "dry run" ]]; then
  if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is not set. Export the admin connection string first." >&2
    echo "  export DATABASE_URL='postgresql://...'" >&2
    exit 2
  fi
  echo "[credentials] checking AWS"
  if ! aws sts get-caller-identity >/dev/null 2>&1; then
    echo "AWS credentials are not available. Titan embedding will fail." >&2
    echo "  export AWS_PROFILE=<your-profile>" >&2
    echo "  aws sso login --profile <your-profile>     # if your org uses SSO" >&2
    echo "  aws sts get-caller-identity                # must print an identity" >&2
    exit 2
  fi
  aws sts get-caller-identity --query 'Arn' --output text
  echo
fi

echo "[1/2] Parsing, chunking and verifying the corpus"
python3 scripts/refresh_chunks.py "${EXTRA[@]}"

echo
echo "[2/2] Done"
if [[ "$MODE" != "dry run" ]]; then
  echo "Restart the deployed service if it caches the index in memory."
fi
