# Quantic infrastructure

Independent CDK app for `QuanticHrAgentStack`. It does not import or modify `CafeFausseApplicationStack` or `AeaSandboxStack`.

Local checks do not call AWS:

```bash
cd infrastructure
npm ci
npm test
npm run build
npm run synth
```

`scripts/synth-infra.sh` is the same offline synth. `scripts/validate-aws-env.sh` is a read-only identity check. `scripts/deploy-sandbox.sh` and the database scripts are authored for a later approval and were not run in Step 1. Deploy asks you to type the stack name, prints the account, region, database, and secret path, and refuses the Café Fausse and AEA stack names.

## What synth creates

- New VPC `10.20.0.0/16`, one NAT gateway, private subnets for the future AgentCore ENIs, and isolated subnets for Aurora.
- Aurora PostgreSQL 17.4 Serverless v2 (0.5–2 ACU), encrypted, IAM auth, database `quantic_hr`, secret `quantic-hr-agent/dev/database/admin`.
- SSM admin host (`t4g.nano`) in a private subnet. Its AMI is an SSM parameter resolved at deploy time.
- Runtime role `quantic-hr-agent-dev-runtime`, scoped to the selected Bedrock models, `rds-db:connect` as `quantic_hr_agent`, and one log group.

SQL under `database/migrations/` is not applied here. The first live session, after approval, is still a read-only check of `pg_available_extensions` before `CREATE EXTENSION vector`.

## Network and MCP

AgentCore VPC mode places ENIs in the private subnets. Inbound `InvokeAgentRuntime` stays on the public AgentCore endpoint and does not enter this VPC. Aurora accepts TCP 5432 only from the runtime security group and the admin host.

One NAT is the path to Bedrock. AWS documents that a public subnet does not give those ENIs internet access, and that a runtime without internet needs ECR, S3, and CloudWatch endpoints. Adding Bedrock interface endpoints on top of that set costs more than one NAT and was not proven without a live runtime. NAT is about $33 per month plus data while the stack exists. Aurora and the admin host cost money only while they are running. Interface endpoints remain the fallback if NAT is rejected before deploy.

The MCP server stays in the same runtime package and speaks stdio to the LangGraph process. AgentCore's own MCP protocol is streamable HTTP, which would make this runtime a second host. Stdio avoids that. Whether `direct_code_deploy` can spawn that child process is unverified until a runtime exists; container packaging is the fallback. No Gateway and no second MCP service are in this stack.

Availability zone names `us-east-2a` and `us-east-2b` are pinned so synth stays offline. `cdk.context.json` lists those names only to satisfy the CDK subset check. It is not a live inventory. Before deploy, confirm the names are `use2-az1` and `use2-az2`. AgentCore rejects other zone IDs in `us-east-2`.

## Later pipeline

This workflow only builds, tests, and synthesizes the CDK app. It has no AWS credentials. Later gates, still on this workflow and still blocked on tests:

1. FastAPI BFF and Vite UI checks, then Render deploy of the BFF. Render stays the host.
2. AgentCore runtime configuration using the stack outputs `RuntimeSubnetIds`, `RuntimeSecurityGroupId`, and `RuntimeRoleArn`.
3. Migration and smoke checks against the new cluster only.

Do not bootstrap a second toolkit. Step 0 already found CDKToolkit in this account and region.
