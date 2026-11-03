# Infrastructure readiness

The synthesized stack is database-only: private Aurora PostgreSQL 17.4 named `quantic_hr_agent`, 0–2 ACU, pause after 300 seconds, encrypted, deletion-protected, and a separate generated secret. It does not include a NAT gateway, AgentCore runtime, admin host, or Café Fausse import.

## Before any deploy

1. `npm test`, `npm run build`, and `npm run synth` pass.
2. `cdk diff` shows only the Quantic stack, with no Café Fausse or AEA changes.
3. The resource list contains no NAT gateway, EIP, internet gateway, VPC endpoint, EC2 instance, AgentCore runtime, customer-managed KMS key, or log group.
4. The estimated paused monthly charge (Aurora storage plus one Secrets Manager secret) is accepted in writing. Compute is $0 only while the instance stays paused.
5. `QUANTIC_ALLOW_AWS_DEPLOY=yes` is set for that approved change set, then `scripts/deploy-sandbox.sh` is used. The script still refuses Café Fausse and AEA stack names.
