#!/usr/bin/env bash
# Read-only identity check. Does not create or change AWS resources.
set -euo pipefail

AWS_PROFILE="${AWS_PROFILE:-AEA-Sandbox-PowerUser}"
AWS_REGION="${AWS_REGION:-us-east-2}"
EXPECTED_ACCOUNT="${EXPECTED_ACCOUNT:-287238357427}"
QUANTIC_PROJECT="${QUANTIC_PROJECT:-quantic-hr-agent}"
QUANTIC_STACK_NAME="${QUANTIC_STACK_NAME:-QuanticHrAgentStack}"

if [[ "$QUANTIC_PROJECT" != "quantic-hr-agent" ]]; then
  echo "ERROR: QUANTIC_PROJECT must be quantic-hr-agent"
  exit 1
fi

case "$QUANTIC_STACK_NAME" in
  CafeFausseApplicationStack|AeaSandboxStack)
    echo "ERROR: Refusing frozen stack $QUANTIC_STACK_NAME"
    exit 1
    ;;
  QuanticHrAgentStack)
    ;;
  *)
    echo "ERROR: Refusing stack $QUANTIC_STACK_NAME"
    exit 1
    ;;
esac

for cmd in aws node npm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: Missing required command: $cmd"
    exit 1
  fi
done

ACCOUNT="$(
  aws sts get-caller-identity \
    --profile "$AWS_PROFILE" \
    --query Account \
    --output text
)"

if [[ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ]]; then
  echo "ERROR: Connected to AWS account $ACCOUNT; expected $EXPECTED_ACCOUNT"
  exit 1
fi

if [[ "$AWS_REGION" != "us-east-2" ]]; then
  echo "ERROR: Refusing region $AWS_REGION"
  exit 1
fi

echo "AWS profile : $AWS_PROFILE"
echo "AWS region  : $AWS_REGION"
echo "AWS account : $ACCOUNT"
echo "Project     : $QUANTIC_PROJECT"
echo "Stack       : $QUANTIC_STACK_NAME"
echo "Validation successful. No resources were changed."
