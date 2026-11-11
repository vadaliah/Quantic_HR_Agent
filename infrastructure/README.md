# Quantic infrastructure

Independent CDK app for `QuanticHrAgentStack`. It does not import or modify `CafeFausseApplicationStack` or `AeaSandboxStack`. Step 1B adds a stdlib AgentCore Hello World runtime on the same VPC. It does not implement RAG, MCP tools, or HR workflows.

Local checks do not call AWS:

```bash
cd infrastructure
npm ci
npm test
npm run build
npm run synth
```

Default `cdk synth` creates a new Aurora cluster. To synthesize against the existing Café Fausse cluster **without modifying it**:

```bash
npm run synth:reuse
```

That mode omits new RDS/secret/admin-host resources and does not add security-group ingress. `scripts/synth-infra.sh` is the default offline synth. `scripts/validate-aws-env.sh` is a read-only identity check. `scripts/predeploy-check.sh` runs local tests, synth, identity, AZ IDs, and a stack/runtime inventory.

`scripts/deploy-sandbox.sh` exits unless `QUANTIC_ALLOW_AWS_DEPLOY=yes`. After that flag, it still refuses Café Fausse and AEA stack names, proves `use2-az1`/`use2-az2`, and deploys only after you type the stack name and `deploy`. Do not provision NAT, Aurora, or AgentCore without that approval.

## What synth creates

- New VPC `10.20.0.0/16`, one NAT gateway, private subnets for the future AgentCore ENIs, and isolated subnets for Aurora.
- Aurora PostgreSQL 17.4 Serverless v2 (0.5–2 ACU), encrypted, IAM auth, database `quantic_hr_agent`, secret `quantic-hr-agent/dev/database/admin`.
- SSM admin host (`t4g.nano`) in a private subnet. Its AMI is an SSM parameter resolved at deploy time.
- Runtime role `quantic-hr-agent-dev-runtime`, scoped to one chat model (`-c quanticChatModel`, default `nova-pro`, alternative `claude-sonnet-4-6`) through its `us.` inference profile and foundation model in us-east-1/us-east-2/us-west-2, Titan Text Embeddings v2 in us-east-2, `rds-db:connect` as `quantic_hr_agent`, and one log group.
- AgentCore runtime `QuanticHrAgent` (`networkMode=VPC`, HTTP `/ping` and `/invocations` on 8080): the repository `Dockerfile` built for linux/arm64 by a CDK `DockerImageAsset` and pushed to the bootstrap ECR repository `cdk-hnb659fds-container-assets-287238357427-us-east-2` during `cdk deploy`. Env: chat/embedding model, region, `DB_HOST`/`DB_PORT`, `DB_NAME=quantic_hr_agent`, `DB_USER=quantic_hr_agent`, IAM DB auth. `-c quanticRuntimeImage=hello-world` falls back to the code-deployed `QuanticHelloWorld` (`runtime/hello_world`).

SQL under `database/migrations/` is not applied here. The first live session, after approval, is still a read-only check of `pg_available_extensions` before `CREATE EXTENSION vector`.

## Network and MCP

AgentCore VPC mode places ENIs in the private subnets. Inbound `InvokeAgentRuntime` stays on the public AgentCore endpoint and does not enter this VPC. Aurora accepts TCP 5432 only from the runtime security group and the admin host.

One NAT is the path to Bedrock. AWS documents that a public subnet does not give those ENIs internet access, and that a runtime without internet needs ECR, S3, and CloudWatch endpoints. Adding Bedrock interface endpoints on top of that set costs more than one NAT and was not proven without a live runtime. NAT is about $33 per month plus data while the stack exists. Aurora and the admin host cost money only while they are running. Interface endpoints remain the fallback if NAT is rejected before deploy.

The MCP server stays in the same runtime package and speaks stdio to the LangGraph process. AgentCore's own MCP protocol is streamable HTTP, which would make this runtime a second host. Stdio avoids that. Whether `direct_code_deploy` can spawn that child process is unverified until a runtime exists; container packaging is the fallback. No Gateway and no second MCP service are in this stack.

Availability zone names `us-east-2a` and `us-east-2b` are pinned so synth stays offline. `cdk.context.json` lists those names only to satisfy the CDK subset check. It is not a live inventory. Before deploy, confirm the names are `use2-az1` and `use2-az2`. AgentCore rejects other zone IDs in `us-east-2`.

## Later pipeline

This workflow only builds, tests, and synthesizes the CDK app. It has no AWS credentials. Later gates, still on this workflow and still blocked on tests:

1. FastAPI BFF and Vite UI checks. Render was dropped on 2026-11-11; BFF/UI hosting stays inside the AWS (CDK) design and is still to be decided.
2. AgentCore runtime configuration using the stack outputs `RuntimeSubnetIds`, `RuntimeSecurityGroupId`, and `RuntimeRoleArn`.
3. Migration and smoke checks against the new cluster only.

Do not bootstrap a second toolkit. Step 0 already found CDKToolkit in this account and region.

## Chat model and teardown context

| Context key | Default | Effect |
| --- | --- | --- |
| `quanticChatModel` | `nova-pro` | Scopes the runtime role to this model. Set the app's `BEDROCK_CHAT_INFERENCE_PROFILE` to the `ChatInferenceProfileId` output. `claude-sonnet-4-6` is the alternative. Confirm Nova Pro access in 287238357427 before deploy. |
| `quanticRuntimeImage` | `agent` | `agent` builds and pushes the Dockerfile image at deploy time; `hello-world` uses the code-deployed Hello World runtime. |
| `quanticDeletionProtection` | `false` | Off for the time-limited demo, so `cdk destroy` deletes Aurora. `true` turns deletion protection on and retains the cluster on stack delete. |
