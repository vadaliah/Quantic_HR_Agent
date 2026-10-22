#!/usr/bin/env bash
# SSM tunnel for SQL against the Quantic cluster only. Do not run in Step 1.
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser}"
AWS_REGION="${AWS_REGION:-us-east-2}"
STACK_NAME="${STACK_NAME:-QuanticHrAgentStack}"
DB_NAME="${DB_NAME:-quantic_hr}"
DB_USER="${DB_USER:-quantic_hr_agent}"
DB_PORT="${DB_PORT:-5432}"
LOCAL_PORT="${LOCAL_PORT:-15432}"
SQL_FILE="${1:-}"

case "$STACK_NAME" in
  CafeFausseApplicationStack|AeaSandboxStack)
    echo "ERROR: Refusing frozen stack $STACK_NAME"
    exit 1
    ;;
  QuanticHrAgentStack)
    ;;
  *)
    echo "ERROR: Refusing stack $STACK_NAME"
    exit 1
    ;;
esac

if [[ -n "$SQL_FILE" && ! -f "$SQL_FILE" ]]; then
  echo "ERROR: SQL file not found: $SQL_FILE"
  exit 1
fi

echo "Target stack ${STACK_NAME}, database ${DB_NAME}, user ${DB_USER}."
read -r -p "Type ${STACK_NAME} to open the tunnel: " reply
if [[ "$reply" != "$STACK_NAME" ]]; then
  echo "Cancelled."
  exit 1
fi

for cmd in aws psql session-manager-plugin nc; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: Required command not found: $cmd"
    exit 1
  }
done

INSTANCE_ID="$(
  aws ec2 describe-instances \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --filters \
      "Name=tag:aws:cloudformation:stack-name,Values=$STACK_NAME" \
      "Name=instance-state-name,Values=running" \
    --query "Reservations[].Instances[?contains(Tags[?Key=='Name'].Value | [0], 'DatabaseAccess/AccessHost')].InstanceId | [0]" \
    --output text
)"

CLUSTER_ID="$(
  aws cloudformation list-stack-resources \
    --stack-name "$STACK_NAME" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query "StackResourceSummaries[?ResourceType=='AWS::RDS::DBCluster'].PhysicalResourceId | [0]" \
    --output text
)"

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "None" ]]; then
  echo "ERROR: Quantic database access host is not running."
  exit 1
fi

DB_HOST="$(
  aws rds describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query "DBClusters[0].Endpoint" \
    --output text
)"

TUNNEL_LOG="$(mktemp "${TMPDIR:-/tmp}/quantic-hr-db-tunnel.XXXXXX")"
TUNNEL_PID=""
cleanup() {
  unset PGPASSWORD || true
  if [[ -n "$TUNNEL_PID" ]]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
    wait "$TUNNEL_PID" 2>/dev/null || true
  fi
  rm -f "$TUNNEL_LOG"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

aws ssm start-session \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$DB_HOST\"],\"portNumber\":[\"$DB_PORT\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}" \
  >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

for _ in {1..20}; do
  if nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null; then
    break
  fi
  if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    cat "$TUNNEL_LOG"
    exit 1
  fi
  sleep 1
done

export PGPASSWORD="$(
  aws rds generate-db-auth-token \
    --hostname "$DB_HOST" \
    --port "$DB_PORT" \
    --region "$AWS_REGION" \
    --username "$DB_USER" \
    --profile "$AWS_PROFILE"
)"

CONNECTION_STRING="host=$DB_HOST hostaddr=127.0.0.1 port=$LOCAL_PORT dbname=$DB_NAME user=$DB_USER sslmode=require"

if [[ -n "$SQL_FILE" ]]; then
  psql "$CONNECTION_STRING" --set ON_ERROR_STOP=1 --file "$SQL_FILE"
else
  psql "$CONNECTION_STRING"
fi
