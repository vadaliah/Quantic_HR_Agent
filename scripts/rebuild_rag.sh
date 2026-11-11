#!/usr/bin/env bash
# Delete every policy chunk and rebuild the vector index from corpus/.
#
# Usage:
#   bash scripts/rebuild_rag.sh                     # full rebuild
#   bash scripts/rebuild_rag.sh --dry-run           # chunk only, no Bedrock, no DB
#   bash scripts/rebuild_rag.sh --plan              # compare shas, change nothing
#   bash scripts/rebuild_rag.sh --corpus <dir>      # use a different corpus root
#   bash scripts/rebuild_rag.sh --skip-verify       # rebuild without the row count
#
# Writes are gated behind QUANTIC_ALLOW_SQL_MIGRATIONS=yes.
set -euo pipefail

# ------------------------------------------------------- locate the repo root
# Accepts scripts/ or infrastructure/scripts/ as the install location.
find_root() {
  local dir="$1"
  for _ in 1 2 3; do
    if [ -f "$dir/scripts/ingest_corpus.py" ]; then printf '%s' "$dir"; return 0; fi
    dir="$(cd "$dir/.." && pwd)"
  done
  return 1
}

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! ROOT="$(find_root "$HERE")"; then
  echo "FAIL: cannot find the repo root from $HERE" >&2
  exit 1
fi
cd "$ROOT"

CORPUS="corpus"
WORK="${QUANTIC_REBUILD_DIR:-/tmp/quantic_rebuild}"
SQL="$WORK/policy_vectors.sql"
RUNNER="infrastructure/database/scripts/run-sql.sh"
MODE="rebuild"
VERIFY="yes"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)     MODE="dry-run" ;;
    --plan)        MODE="plan" ;;
    --skip-verify) VERIFY="no" ;;
    --corpus)      shift; CORPUS="${1:?--corpus needs a directory}" ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

STEP=0
TOTAL=6
say()  { STEP=$((STEP + 1)); printf '\n\033[1m[%d/%d] %s\033[0m\n' "$STEP" "$TOTAL" "$*"; }
ok()   { printf '       %s\n' "$*"; }
warn() { printf '       ! %s\n' "$*" >&2; }
die()  { printf '       FAIL: %s\n' "$*" >&2; exit 1; }

mkdir -p "$WORK"

printf '\033[1mRAG rebuild\033[0m\n'
ok "repo root:  $ROOT"
ok "corpus:     $CORPUS"
ok "work dir:   $WORK"
ok "mode:       $MODE"
if [ -n "${QUANTIC_ALLOW_SQL_MIGRATIONS:-}" ]; then
  ok "database:   writes ENABLED"
else
  ok "database:   writes disabled (set QUANTIC_ALLOW_SQL_MIGRATIONS=yes)"
fi

# ------------------------------------------------------ 1. corpus inventory
say "Scanning the corpus"
[ -d "$CORPUS" ] || die "no $CORPUS/ directory under $ROOT"

python3 - "$CORPUS" <<'PY' || die "corpus scan failed"
import re, sys
from pathlib import Path

SECTION_RE = re.compile(r"^([A-Za-z]?\d+(?:\.\d+)*)\.?\s+(.*)$")
HEAD = re.compile(r"^(#{2,3})\s+(.*)$")
EXTS = {".md", ".html", ".htm", ".txt", ".pdf"}

corpus = Path(sys.argv[1])
files = sorted(p for p in corpus.rglob("*") if p.is_file() and p.suffix.lower() in EXTS)
if not files:
    print(f"       FAIL: no ingestible files under {corpus}", file=sys.stderr)
    raise SystemExit(1)

unparsed = []
for path in files:
    if path.suffix.lower() in (".html", ".htm"):
        text = path.read_text(encoding="utf-8", errors="replace")
        heads = re.findall(r"(?i)<h[1-3][^>]*>(.*?)</h[1-3]>", text, flags=re.S)
        heads = [re.sub(r"<[^>]+>", "", h).strip() for h in heads]
    else:
        heads = [m.group(2).strip() for m in (HEAD.match(l.strip()) for l in
                 path.read_text(encoding="utf-8", errors="replace").splitlines()) if m]
    for heading in heads:
        if not SECTION_RE.match(heading):
            unparsed.append(f"{path.name}: {heading[:60]}")

print(f"       {len(files)} files")
print(f"       {len(unparsed)} headings without a leading number"
      + (f"  (first: {unparsed[0]})" if unparsed else "  — all headings numbered"))
PY

# ------------------------------------------------- 2. chunk and embed (long)
if [ "$MODE" = "plan" ]; then
  say "Plan only: comparing local shas with Aurora"
  uv run python scripts/ingest_corpus.py --corpus "$CORPUS" --plan || die "plan failed"
  printf '\nDone. Nothing was changed.\n'
  exit 0
fi

if [ "$MODE" = "dry-run" ]; then
  say "Chunking only (no Bedrock, no database)"
  uv run python scripts/ingest_corpus.py --corpus "$CORPUS" --dry-run || die "chunking failed"
  ok "dry run complete — nothing written"
  printf '\nDone.\n'
  exit 0
fi

say "Chunking and embedding the corpus"
ok "this is the slow step: Titan embeds in batches of 32, expect 1-3 minutes"
START=$(date +%s)
uv run python scripts/ingest_corpus.py --corpus "$CORPUS" --out "$SQL" \
  || die "ingest failed — see the output above"
ELAPSED=$(( $(date +%s) - START ))
[ -s "$SQL" ] || die "SQL file is empty: $SQL"
ok "finished in ${ELAPSED}s"
ok "SQL: $SQL  ($(wc -c < "$SQL" | tr -d ' ') bytes)"
ok "chunk INSERT statements: $(grep -c 'INSERT INTO policy_chunks' "$SQL")"

# ------------------------------------------------------- 3. section id check
say "Checking section ids"
ZERO=$(grep -c "s0'" "$SQL" || true)
if [ "$ZERO" -gt 0 ]; then
  die "$ZERO chunks still carry section_id '0' — check SECTION_RE in
       scripts/ingest_corpus.py accepts a trailing dot (## 1. Observed Holidays)"
fi
ok "no chunk has section_id '0'"

# ------------------------------------------------------------ 4. wipe table
say "Deleting existing chunks"
cat > "$WORK/00_truncate.sql" <<'SQL'
-- Full rebuild: the corpus is the source of truth for this table.
DELETE FROM policy_chunks;
SQL
if [ -n "${QUANTIC_ALLOW_SQL_MIGRATIONS:-}" ]; then
  bash "$RUNNER" "$WORK/00_truncate.sql" || die "delete failed"
  ok "policy_chunks emptied"
else
  warn "would run: bash $RUNNER $WORK/00_truncate.sql"
fi

# ------------------------------------------------------------- 5. load vectors
say "Loading the new vectors"
if [ ! -f "$RUNNER" ]; then
  die "runner not found: $RUNNER (expected at the repo root)"
fi
bash "$RUNNER" --check "$SQL" || die "the runner rejected the SQL"
ok "SQL passed the runner's check"
if [ -n "${QUANTIC_ALLOW_SQL_MIGRATIONS:-}" ]; then
  bash "$RUNNER" "$SQL" || die "load failed"
  ok "vectors loaded"
else
  warn "would run: bash $RUNNER $SQL"
fi

# ----------------------------------------------------------------- 6. verify
say "Verifying"
if [ "$VERIFY" = "yes" ] && [ -n "${QUANTIC_ALLOW_SQL_MIGRATIONS:-}" ]; then
  cat > "$WORK/99_verify.sql" <<'SQL'
SELECT count(*) AS chunks_loaded FROM policy_chunks;
SQL
  bash "$RUNNER" "$WORK/99_verify.sql" || warn "row count unavailable"
else
  ok "skipped (no writes performed, or --skip-verify)"
fi

cat <<'NEXT'

Done.
  bash scripts/app.sh start
  python3 evaluation/run_eval.py --fresh-thread
NEXT
