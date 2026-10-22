#!/usr/bin/env bash
# Read-only pre-deployment checks. Does not create, update, start, or delete AWS resources.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$INFRA_DIR/.." && pwd)"

export AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser}"
export AWS_REGION="${AWS_REGION:-us-east-2}"
export EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-287238357427}"
export QUANTIC_PROJECT="${QUANTIC_PROJECT:-quantic-hr-agent}"
export QUANTIC_STACK_NAME="${QUANTIC_STACK_NAME:-QuanticHrAgentStack}"

echo "== Local Hello World tests =="
python3 -m unittest discover -s "$REPO_DIR/runtime/hello_world" -p 'test_*.py'

echo
echo "== Offline CDK tests and synth =="
cd "$INFRA_DIR"
npm test
npm run build
npm run synth

echo
echo "== Read-only AWS identity =="
"$SCRIPT_DIR/validate-aws-env.sh"

ACCOUNT="$(
  aws sts get-caller-identity \
    --profile "$AWS_PROFILE" \
    --query Account \
    --output text
)"
export QUANTIC_ACCOUNT="$ACCOUNT"
export QUANTIC_REGION="$AWS_REGION"
npx tsx "$SCRIPT_DIR/check-deploy-target.ts"

echo
echo "== AgentCore availability zone IDs =="
ZONE_JSON="$(
  aws ec2 describe-availability-zones \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query 'AvailabilityZones[].{name:ZoneName,id:ZoneId}' \
    --output json
)"
npx tsx "$SCRIPT_DIR/check-availability-zones.ts" "$ZONE_JSON"

echo
echo "== Existing stacks (read-only) =="
aws cloudformation list-stacks \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE UPDATE_ROLLBACK_COMPLETE \
  --query "StackSummaries[?contains(['CafeFausseApplicationStack','AeaSandboxStack','QuanticHrAgentStack','CDKToolkit'], StackName)].{name:StackName,status:StackStatus}" \
  --output table

if aws cloudformation describe-stacks \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --stack-name "$QUANTIC_STACK_NAME" >/dev/null 2>&1; then
  echo "NOTE: $QUANTIC_STACK_NAME already exists. A later approved deploy would update it."
else
  echo "$QUANTIC_STACK_NAME is not deployed. An approved deploy would create it."
fi

echo
echo "== AgentCore runtimes (read-only) =="
aws bedrock-agentcore-control list-agent-runtimes \
  --profile "$AWS_PROFILE" \
  --region "$AWS_REGION" \
  --output table

echo
echo "Pre-deployment checks finished. No AWS resources were created or changed."
echo "STOP: do not run scripts/deploy-sandbox.sh until this change set is approved."
