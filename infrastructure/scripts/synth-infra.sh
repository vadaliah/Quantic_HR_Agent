#!/usr/bin/env bash
# Local synth only. Does not call AWS.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

export CDK_DEFAULT_ACCOUNT="${CDK_DEFAULT_ACCOUNT:-287238357427}"
export CDK_DEFAULT_REGION="${CDK_DEFAULT_REGION:-us-east-2}"

cd "$INFRA_DIR"
npm run build
npm run synth
echo "Offline synth completed for QuanticHrAgentStack."
