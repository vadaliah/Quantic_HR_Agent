#!/usr/bin/env bash
# Guarded deploy. Do not run until the Step 1B change set is explicitly approved.
set -euo pipefail

if [[ "${QUANTIC_ALLOW_AWS_DEPLOY:-}" != "yes" ]]; then
  echo "ERROR: Cost-first strategy blocks AWS deploy."
  echo "CDK code is preserved for later. Refusing to provision billable resources."
  echo "A later paid-infra approval must set QUANTIC_ALLOW_AWS_DEPLOY=yes."
  exit 1
fi

AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser}"
AWS_REGION="${AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-287238357427}"
QUANTIC_PROJECT="${QUANTIC_PROJECT:-quantic-hr-agent}"
QUANTIC_STACK_NAME="${QUANTIC_STACK_NAME:-QuanticHrAgentStack}"

case "$QUANTIC_STACK_NAME" in
  CafeFausseApplicationStack|AeaSandboxStack)
    echo "ERROR: Refusing frozen stack $QUANTIC_STACK_NAME"
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ACCOUNT="$(
  aws sts get-caller-identity \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query Account \
    --output text
)"

export QUANTIC_PROJECT QUANTIC_STACK_NAME
export QUANTIC_ACCOUNT="$ACCOUNT"
export QUANTIC_REGION="$AWS_REGION"
export CDK_DEFAULT_ACCOUNT="$ACCOUNT"
export CDK_DEFAULT_REGION="$AWS_REGION"

cd "$INFRA_DIR"
npx tsx scripts/check-deploy-target.ts

ZONE_JSON="$(
  aws ec2 describe-availability-zones \
    --profile "$AWS_PROFILE" \
    --region "$AWS_REGION" \
    --query 'AvailabilityZones[].{name:ZoneName,id:ZoneId}' \
    --output json
)"
npx tsx scripts/check-availability-zones.ts "$ZONE_JSON"

echo
echo "Planned change set (nothing has been deployed yet)"
echo "  project : $QUANTIC_PROJECT"
echo "  stack   : $QUANTIC_STACK_NAME"
echo "  account : $ACCOUNT"
echo "  region  : $AWS_REGION"
echo "  database: quantic_hr"
echo "  secret  : quantic-hr-agent/dev/database/admin"
echo "  profile : $AWS_PROFILE"
echo
echo "Blocked stacks: CafeFausseApplicationStack, AeaSandboxStack"
echo

read -r -p "Type ${QUANTIC_STACK_NAME} to deploy, or anything else to cancel: " reply
if [[ "$reply" != "$QUANTIC_STACK_NAME" ]]; then
  echo "Deployment cancelled."
  exit 1
fi

npx aws-cdk diff --profile "$AWS_PROFILE"
read -r -p "Apply the diff above? Type deploy to continue: " confirm
if [[ "$confirm" != "deploy" ]]; then
  echo "Deployment cancelled."
  exit 1
fi

npx aws-cdk deploy "$QUANTIC_STACK_NAME" \
  --profile "$AWS_PROFILE" \
  --require-approval broadening
