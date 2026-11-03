# Quantic infrastructure

Independent CDK app for `QuanticHrAgentStack`. It creates a new Aurora PostgreSQL cluster and does not import or modify `CafeFausseApplicationStack` or `AeaSandboxStack`.

Local checks do not call AWS:

```bash
cd infrastructure
npm ci
npm test
npm run build
npm run synth
```

`cdk diff` is read-only. `scripts/deploy-sandbox.sh` exits unless `QUANTIC_ALLOW_AWS_DEPLOY=yes`, then still refuses Café Fausse and AEA stack names and any database mode other than `create`. It deploys only after you type the stack name and `deploy`.

## What synth creates

- New VPC `10.20.0.0/16` with two isolated subnets. No NAT gateway, internet gateway, public subnet, VPC endpoint, or peering connection.
- Aurora PostgreSQL 17.4 Serverless v2, 0–2 ACU, automatic pause after 300 seconds. Storage encryption uses the AWS-managed RDS key. Deletion protection is on. The cluster is not publicly accessible.
- Empty database `quantic_hr_agent` and a generated admin secret `quantic-hr-agent/dev/database/admin`. No schema, extension, table, or application role is applied.
- The database security group has no inbound rule. Nothing can connect until a later change adds one.

SQL under `database/migrations/` is not applied by this stack. `database/scripts/create-quantic-db.sh` refuses to run so it cannot target Café Fausse.

## Recurring charges if this stack is deployed

US East (Ohio) public price list, checked 3 Nov 2026. Aurora rates are from the RDS offer published 2026-10-29. Secrets Manager rates are from the offer published 2026-09-11. These are list prices before tax or credits.

- Aurora PostgreSQL Serverless v2, Standard: $0.12 per ACU-hour. At 0 ACU the compute charge is $0. A continuous 0.5 ACU floor would be about $43.80 per month; this template does not set that floor.
- Aurora Standard storage: $0.10 per consumed GB-month. I/O: $0.20 per million requests. Backup storage beyond the included amount: $0.021 per GB-month. Retention is 1 day. The template does not select I/O-Optimized storage.
- One Secrets Manager secret: $0.40 per month, plus $0.05 per 10,000 API requests.
- VPC, subnets, route tables, the security group, and the subnet group have no hourly charge. There is no NAT gateway, public IPv4 address, interface endpoint, EC2 instance, customer-managed KMS key, or AgentCore runtime in the template.

An idle paused cluster therefore bills the secret plus whatever storage Aurora records for the empty volume. The exact starting volume size is known only after creation. NAT, which this stack does not create, is a separate charge of about $0.045 per hour.

Availability zone names `us-east-2a` and `us-east-2b` are pinned so synth stays offline. `cdk.context.json` is not a live inventory.

Do not bootstrap a second toolkit. Step 0 already found CDKToolkit in this account and region.
