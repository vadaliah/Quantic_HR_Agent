#!/usr/bin/env bash
# Manage the Quantic HR Agent as background daemons.
#
#   bash scripts/app.sh start     kill stale processes, warm the cluster, start both
#   bash scripts/app.sh stop      stop both
#   bash scripts/app.sh restart   stop then start
#   bash scripts/app.sh status    what is running and whether it responds
#   bash scripts/app.sh logs      tail the API log
#
# Servers run detached, so this script exits and they keep running. PID files in
# .run/ tell stop and status which processes they own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
RUN_DIR="$ROOT/.run"
API_LOG="$RUN_DIR/api.log"
UI_LOG="$RUN_DIR/ui.log"
API_PID_FILE="$RUN_DIR/api.pid"
UI_PID_FILE="$RUN_DIR/ui.pid"

mkdir -p "$RUN_DIR"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

kill_port() {
  local port="$1" pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  [[ -z "$pids" ]] && return 0
  echo "    port $port held by: $pids"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 2
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    warn "port $port still held; SIGKILL"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

do_stop() {
  log "Stopping"
  for f in "$API_PID_FILE" "$UI_PID_FILE"; do
    [[ -f "$f" ]] || continue
    pid="$(cat "$f")"
    if alive "$pid"; then kill "$pid" 2>/dev/null || true; echo "    stopped pid $pid"; fi
    rm -f "$f"
  done
  kill_port "$API_PORT"
  kill_port "$UI_PORT"
  pkill -f "quantic_hr.mcp_server" 2>/dev/null || true
  echo "    done"
}

do_start() {
  do_stop

  log "AWS environment"
  export AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser-287238357427}"
  export AWS_REGION="${AWS_REGION:-us-east-2}"
  export BEDROCK_CHAT_INFERENCE_PROFILE="${BEDROCK_CHAT_INFERENCE_PROFILE:-us.amazon.nova-pro-v1:0}"
  export BEDROCK_EMBEDDING_MODEL="${BEDROCK_EMBEDDING_MODEL:-amazon.titan-embed-text-v2:0}"

  if ! aws sts get-caller-identity --profile "$AWS_PROFILE" >/dev/null 2>&1; then
    warn "AWS session invalid. Run: aws sso login --profile $AWS_PROFILE"
    die  "cannot start without credentials"
  fi
  echo "    $AWS_PROFILE  $AWS_REGION"

  export CLUSTER_ARN="${CLUSTER_ARN:-$(aws rds describe-db-clusters \
    --db-cluster-identifier quantichragentstack-databaseaurorapostgres6560ef93-h8yvdkzw8voy \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --query 'DBClusters[0].DBClusterArn' --output text)}"
  export SECRET_ARN="${SECRET_ARN:-$(aws secretsmanager describe-secret \
    --secret-id quantic-hr-agent/dev/database/admin \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" --query ARN --output text)}"
  [[ "$CLUSTER_ARN" == arn:* ]] || die "CLUSTER_ARN did not resolve"
  [[ "$SECRET_ARN"  == arn:* ]] || die "SECRET_ARN did not resolve"
  echo "    cluster and secret resolved"

  cat > "$RUN_DIR/env.sh" <<ENVEOF
export AWS_PROFILE='$AWS_PROFILE'
export AWS_REGION='$AWS_REGION'
export BEDROCK_CHAT_INFERENCE_PROFILE='$BEDROCK_CHAT_INFERENCE_PROFILE'
export BEDROCK_EMBEDDING_MODEL='$BEDROCK_EMBEDDING_MODEL'
export CLUSTER_ARN='$CLUSTER_ARN'
export SECRET_ARN='$SECRET_ARN'
ENVEOF

  log "Dependencies"
  uv sync --group dev >/dev/null && echo "    python synced"
  if [[ ! -d frontend/node_modules ]]; then
    npm --prefix frontend install >/dev/null && echo "    node_modules installed"
  else
    echo "    node_modules present"
  fi

  log "Waking the cluster"
  if uv run python - <<'PY' >/dev/null 2>&1
import time
from quantic_hr import db
for _ in range(6):
    if db.health().get("ok"):
        raise SystemExit(0)
    time.sleep(10)
raise SystemExit(1)
PY
  then echo "    cluster warm"
  else warn "cluster did not wake; the first question may fail"; fi

  # macOS has no setsid. nohup plus a subshell detaches from this shell, and
  # disown keeps the job out of the shell's job table.
  log "Starting the API on $API_PORT"
  : > "$API_LOG"
  set -a; source "$RUN_DIR/env.sh"; set +a
  nohup uv run uvicorn quantic_hr.bff:app --app-dir src \
      --host 127.0.0.1 --port "$API_PORT" >> "$API_LOG" 2>&1 &
  echo $! > "$API_PID_FILE"
  disown || true
  echo "    api pid $(cat "$API_PID_FILE")  log $API_LOG"

  for _ in {1..25}; do
    curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 1
  done
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "    /health responding"
  else
    warn "/health not responding; check $API_LOG"
  fi

  log "Starting the UI on $UI_PORT"
  : > "$UI_LOG"
  nohup npm --prefix frontend run dev -- --port "$UI_PORT" >> "$UI_LOG" 2>&1 &
  echo $! > "$UI_PID_FILE"
  disown || true
  echo "    ui pid $(cat "$UI_PID_FILE")  log $UI_LOG"
  sleep 3

  cat <<EOF

Running detached. This shell is free.

  API   http://127.0.0.1:$API_PORT/health
  UI    http://localhost:$UI_PORT/
  logs  $API_LOG  ·  $UI_LOG

  bash scripts/app.sh status | logs | stop

EOF
}

do_status() {
  log "Status"
  for entry in "api:$API_PORT:$API_PID_FILE:$API_LOG" "ui:$UI_PORT:$UI_PID_FILE:$UI_LOG"; do
    IFS=: read -r name port pidfile logfile <<< "$entry"
    printf '  %-4s port %-5s ' "$name" "$port"
    pids="$(lsof -ti :"$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then printf 'listening (%s)' "$pids"; else printf 'NOT listening'; fi
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      if alive "$pid"; then printf '  · pid %s alive' "$pid"
      else printf '  · pid %s stale' "$pid"; fi
    fi
    printf '\n'
  done
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo; echo "  /health:"; curl -s "http://127.0.0.1:${API_PORT}/health"; echo
  fi
}

do_logs() {
  [[ -f "$API_LOG" ]] || die "no api log yet; run start"
  tail -n 40 -f "$API_LOG"
}

case "${1:-status}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  logs)    do_logs ;;
  *) echo "Usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
