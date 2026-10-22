#!/usr/bin/env bash
# Creates the IAM database role on the Quantic cluster. Do not run in Step 1.
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser}"
AWS_REGION="${AWS_REGION:-us-east-2}"
STACK_NAME="${STACK_NAME:-QuanticHrAgentStack}"
DB_NAME="${DB_NAME:-quantic_hr}"
DB_ADMIN_USER="${DB_ADMIN_USER:-quantic_hr_admin}"
DB_RUNTIME_USER="${DB_RUNTIME_USER:-quantic_hr_agent}"
DB_PORT="${DB_PORT:-5432}"
LOCAL_PORT="${LOCAL_PORT:-15432}"
SECRET_ID="${SECRET_ID:-quantic-hr-agent/dev/database/admin}"

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

if [[ "$SECRET_ID" != "quantic-hr-agent/dev/database/admin" ]]; then
  echo "ERROR: Refusing secret $SECRET_ID"
  exit 1
fi

echo "This script opens an SSM tunnel and creates ${DB_RUNTIME_USER} on ${DB_NAME}."
echo "It is not part of the Step 1 local test run."
read -r -p "Type ${STACK_NAME} to continue: " reply
if [[ "$reply" != "$STACK_NAME" ]]; then
  echo "Cancelled."
  exit 1
fi

for cmd in aws psql session-manager-plugin nc python3; do
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
      "Name=tag:Name,Values=*DatabaseAccess/AccessHost*" \
    --query "Reservations[].Instances[].InstanceId | [0]" \
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

DB_HOST="$(
  aws rds describe-db-clusters \
    --db-cluster-identifier "$CLUSTER_ID" \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query "DBClusters[0].Endpoint" \
    --output text
)"

ADMIN_SECRET="$(
  aws secretsmanager get-secret-value \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --secret-id "$SECRET_ID" \
    --query SecretString \
    --output text
)"

export PGPASSWORD="$(
  printf '%s' "$ADMIN_SECRET" |
    python3 -c 'import json,sys; print(json.load(sys.stdin)["password"])'
)"

TUNNEL_LOG="$(mktemp "${TMPDIR:-/tmp}/quantic-hr-bootstrap.XXXXXX")"
aws ssm start-session \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"$DB_HOST\"],\"portNumber\":[\"$DB_PORT\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}" \
  >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

cleanup() {
  unset PGPASSWORD || true
  kill "$TUNNEL_PID" 2>/dev/null || true
  wait "$TUNNEL_PID" 2>/dev/null || true
  rm -f "$TUNNEL_LOG"
}
trap cleanup EXIT INT TERM

for _ in {1..30}; do
  nc -z 127.0.0.1 "$LOCAL_PORT" 2>/dev/null && break
  kill -0 "$TUNNEL_PID" 2>/dev/null || {
    cat "$TUNNEL_LOG"
    exit 1
  }
  sleep 1
done

psql \
  "host=$DB_HOST hostaddr=127.0.0.1 port=$LOCAL_PORT dbname=$DB_NAME user=$DB_ADMIN_USER sslmode=require" \
  --set ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '$DB_RUNTIME_USER') THEN
    EXECUTE 'CREATE ROLE $DB_RUNTIME_USER LOGIN';
  END IF;
END
\$\$;

GRANT rds_iam TO $DB_RUNTIME_USER;
GRANT CONNECT ON DATABASE $DB_NAME TO $DB_RUNTIME_USER;
GRANT USAGE ON SCHEMA public TO $DB_RUNTIME_USER;
SQL

echo "IAM role ${DB_RUNTIME_USER} is ready on ${DB_NAME}."
