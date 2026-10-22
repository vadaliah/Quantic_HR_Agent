# Infrastructure readiness

Checked with `npm run build`, `npm test`, `npm run synth`, and `npm run synth:reuse`. No AWS resources were provisioned.

## Deployment blockers (actual)

1. **No paid-infra approval.** `deploy-sandbox.sh` still creates at least a VPC, NAT, EIP, runtime role, log group, and AgentCore Hello World in both database modes. That starts NAT/EIP charges (~$37/month) even when Aurora is reused. **Resolution:** keep the stack undeployed until a written yes on that bill; then run the existing gated deploy script.

2. **AZ IDs not re-checked at deploy time in this change.** Synth pins `us-east-2a/b`. AgentCore requires `use2-az1`/`use2-az2` (confirmed in the Oct 20 read-only inventory). **Resolution:** `scripts/predeploy-check.sh` / `check-availability-zones.ts` before any deploy.

3. **Reuse mode cannot open TCP 5432 to Café Aurora.** The Café security group is imported `mutable: false`. The Hello World runtime sits in a new Quantic VPC. No peering and no ingress are synthesized, by design. **Resolution:** do not expect DB connectivity from this stack until a separate, approved Café SG/network change. Hello World does not need the database.

4. **Café (and AEA) clusters are stopped.** Using the existing database requires `start-db-cluster`, which bills ACUs and was not done. Stopped clusters also auto-start after seven days on their own. **Resolution:** treat start/stop as an explicit ops action, not part of this CDK baseline.

5. **Café SSM interface endpoints are drifted.** CloudFormation lists them; EC2 does not. An SSM admin tunnel to Café Aurora may fail until that Café stack is repaired (out of scope; would mutate Café). **Resolution:** local Postgres for app work; do not block this baseline on the tunnel.

6. **`pgvector` on Café Aurora is unverified.** Confirming it requires starting the cluster and running SQL. **Resolution:** first live session, after approval, remains `SELECT` on `pg_available_extensions`.

There is no TypeScript, unit-test, or offline-synth blocker.
