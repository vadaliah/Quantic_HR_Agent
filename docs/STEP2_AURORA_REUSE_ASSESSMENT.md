# Step 2 — Read-only Aurora reuse assessment (October 20, 2026)

## Decision and scope
Café Fausse application is effectively complete. User prefers reusing its existing Aurora PostgreSQL cluster for Quantic HR Agent to avoid unnecessary paid duplication, but **database structure/design is NOT ready**. This step is **discovery ONLY**. Do not create `quantic_hr`, alter roles/schema, start/stop clusters, create snapshots, change auto-pause or security groups, deploy CDK, or incur charges. Ask for explicit approval after reviewing findings before any AWS mutation.

This direction **supersedes** the assumption in `docs/AURORA_ARCHITECTURE_DECISION.md` that Quantic necessarily needs a separate newly provisioned cluster. Continue PostgreSQL/pgvector as target; local PostgreSQL is acceptable for isolated automated tests. Keep all original CDK work undeployed as an optional path; do not remove it.

## Cursor task — AWS read-only investigation
Use a local authenticated AWS session; never upload credentials or secrets to a cloud agent. If the AWS profile is missing, report the blocker and local setup needed, without inventing findings. Verify account `287238357427`, region `us-east-2`, and target resources; inspect `CafeFausseApplicationStack` and any relevant `AeaSandboxStack` dependencies **without changing either**.

Report:
1. **Inventory / dependencies**: cluster identifier/ARN, engine/version, serverless min/max capacity, lifecycle state, associated CloudFormation stack, VPC/subnets/SGs, secrets references (never secret values), DB instance(s); confirm Café Fausse vs AEA are separate and identify what cannot be deleted safely.
2. **Costs**: which resources remain charged while stopped or paused (Aurora storage/backup, NAT gateways, EIPs, VPC endpoints, EC2, CloudWatch); estimate incremental Quantic costs separately from unavoidable existing charges, and identify likely waste. Avoid implying snapshots/free-tier are free.
3. **Auto-pause feasibility**: Aurora PostgreSQL 17.4 version support, minimum ACU configuration, limitations of pause/resume and potential long-running DB connections; determine what configuration changes would be needed without applying them.
4. **Snapshot/retention plan**: distinguish final manual cluster snapshot vs current automated backups, restore procedure, approximate snapshot storage cost, and whether cluster must be started to make the intended snapshot. No snapshots yet.
5. **Connectivity strategy**: how the eventual shared Quantic application and (if needed) AgentCore connect to this existing private Aurora cluster; security, IAM auth options, required network access, the lowest cost alternative to a new NAT, and group access without opening Postgres to public internet.
6. **CDK changes only as a proposal**: how to reference/import existing Aurora cluster and omit new Aurora/NAT/admin resources in Quantic deployment config, preserving existing infrastructure stacks and drift safety. Identify any configuration changes that would affect Café Fausse.
7. **Data modeling deferred**: do not select tables, make migrations, provision the HR database, ingest documents, or prescribe HR schema. List data-design decisions to review later (HR entities, access controls, RAG vectors/citations, retention) without committing to a schema.

## Deliverable
Commit findings and an explicit no-change proposed migration/reuse plan to `docs/AURORA_REUSE_FINDINGS.md` on a feature branch. Clearly mark **observed vs inferred vs unverified**, include commands/source evidence (omit secrets), approximate costs, and a short approval checklist for later mutations. Push branch and optionally update existing draft PR only if appropriate; don't merge without user consent.

## Constraints
- No AWS mutations, no billable provisioning, no snapshots/start/stop, no new Quantic DB/schema/roles.
- No alteration or deletion of Café Fausse/AEA stacks/resources.
- Keep November 15 deadline and allow local application/MCP/RAG development in parallel; shared AWS DB provisioning comes *after* HR data-model review and a user approval gate.
