#!/usr/bin/env bash
# Manage the Quantic HR Agent as background daemons.
#
#   bash scripts/app.sh start     kill stale processes, warm the cluster, start both
#   bash scripts/app.sh stop      stop both
#   bash scripts/app.sh restart   stop then start
#   bash scripts/app.sh status    what is running and whether it responds
#   bash scripts/app.sh logs      tail both logs
#
# The servers run detached: this script exits and they keep running. PID files
# live in .run/ so stop and status know what they own.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
UI_PORT="${UI_PORT:-5173}"
RUN_DIR="$ROOT/.run"
LOG_DIR="$ROOT/.run"
API_LOG="$LOG_DIR/api.log"
UI_LOG="$LOG_DIR/ui.log"
API_PID_FILE="$RUN_DIR/api.pid"
UI_PID_FILE="$RUN_DIR/ui.pid"

mkdir -p "$RUN_DIR"

log()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------- helpers
pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pid_on_port() {
  lsof -ti :"$1" 2>/dev/null || true
}

kill_port() {
  local port="$1" pids
  pids="$(pid_on_port "$port")"
  [[ -z "$pids" ]] && return 0
  echo "    port $port held by: $pids"
  # shellcheck disable=SC2086
  kill $pids 2>/dev/null || true
  sleep 2
  pids="$(pid_on_port "$port")"
  if [[ -n "$pids" ]]; then
    warn "port $port still held; SIGKILL"
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

# --------------------------------------------------------------------- stop
do_stop() {
  log "Stopping"
  for f in "$API_PID_FILE" "$UI_PID_FILE"; do
    if [[ -f "$f" ]]; then
      pid="$(cat "$f")"
      if pid_alive "$pid"; then
        kill "$pid" 2>/dev/null || true
        echo "    stopped pid $pid ($(basename "$f"))"
      fi
      rm -f "$f"
    fi
  done
  kill_port "$API_PORT"
  kill_port "$UI_PORT"
  pkill -f "quantic_hr.mcp_server" 2>/dev/null || true
  echo "    done"
}

# -------------------------------------------------------------------- start
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

  # Persist the environment so status/restart can reuse it and so the MCP
  # subprocess inherits the same values.
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
  then
    echo "    cluster warm"
  else
    warn "cluster did not wake; the first question may fail"
  fi

  # ------------------------------------------------------------ launch daemons
  # setsid detaches from this shell so the process survives the script exiting.
  log "Starting the API on $API_PORT"
  : > "$API_LOG"
  ( setsid env $(sed -n 's/^export //p' "$RUN_DIR/env.sh" | tr '\n' ' ') \
      uv run uvicorn quantic_hr.bff:app --app-dir src \
      --host 127.0.0.1 --port "$API_PORT" \
      >> "$API_LOG" 2>&1 & echo $! > "$API_PID_FILE" )
  API_PID="$(cat "$API_PID_FILE")"
  echo "    api pid $API_PID  log $API_LOG"

  for _ in {1..25}; do
    curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1 && break
    sleep 1
  done
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo "    /health responding"
  else
    warn "/health not responding yet; check $API_LOG"
  fi

  log "Starting the UI on $UI_PORT"
  : > "$UI_LOG"
  ( setsid npm --prefix frontend run dev -- --port "$UI_PORT" \
      >> "$UI_LOG" 2>&1 & echo $! > "$UI_PID_FILE" )
  UI_PID="$(cat "$UI_PID_FILE")"
  echo "    ui pid $UI_PID  log $UI_LOG"
  sleep 3

  cat <<EOF

Running detached. This shell is free.

  API   http://127.0.0.1:$API_PORT/health
  UI    http://localhost:$UI_PORT/
  logs  $API_LOG  ·  $UI_LOG

  bash scripts/app.sh status
  bash scripts/app.sh logs
  bash scripts/app.sh stop

EOF
}

# ------------------------------------------------------------------- status
do_status() {
  log "Status"
  for entry in "api:$API_PORT:$API_PID_FILE:$API_LOG" "ui:$UI_PORT:$UI_PID_FILE:$UI_LOG"; do
    IFS=: read -r name port pidfile logfile <<< "$entry"
    printf '  %-4s port %-5s ' "$name" "$port"
    pids="$(pid_on_port "$port")"
    if [[ -n "$pids" ]]; then
      printf 'listening (pid %s)' "$pids"
    else
      printf 'NOT listening'
    fi
    if [[ -f "$pidfile" ]]; then
      pid="$(cat "$pidfile")"
      if pid_alive "$pid"; then printf '  · pidfile %s alive' "$pid"
      else printf '  · pidfile %s stale' "$pid"; fi
    fi
    printf '\n'
  done

  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    echo
    echo "  /health:"
    curl -s "http://127.0.0.1:${API_PORT}/health"
    echo
  fi
}

# --------------------------------------------------------------------- logs
do_logs() {
  [[ -f "$API_LOG" ]] || die "no api log yet; run start"
  log "API log (Ctrl-C to stop tailing)"
  tail -n 40 -f "$API_LOG"
}

# --------------------------------------------------------------------- main
case "${1:-status}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  logs)    do_logs ;;
  *) echo "Usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
