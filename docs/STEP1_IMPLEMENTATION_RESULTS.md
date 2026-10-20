# Step 1 implementation results

**Status:** Local code and tests only. Nothing was deployed, started, or changed in AWS. Café Fausse and AEA stay as they were. Stop here for review.

## Files added

CDK app under `infrastructure/`, copied from Café Fausse patterns and renamed for Quantic:

| Quantic file | Café Fausse source |
|---|---|
| `infrastructure/bin/infrastructure.ts` | `infrastructure/bin/infrastructure.ts` |
| `infrastructure/lib/infrastructure-stack.ts` | `infrastructure/lib/infrastructure-stack.ts` |
| `infrastructure/lib/constructs/network.ts` | `infrastructure/lib/constructs/network.ts` |
| `infrastructure/lib/constructs/database.ts` | `infrastructure/lib/constructs/database.ts` |
| `infrastructure/lib/constructs/database-access.ts` | `infrastructure/lib/constructs/database-access.ts` |
| `infrastructure/cdk.json` | `infrastructure/cdk.json` |
| `infrastructure/scripts/validate-aws-env.sh` | `infrastructure/scripts/validate-aws-env.sh` |
| `infrastructure/scripts/synth-infra.sh` | `infrastructure/scripts/synth-infra.sh` |
| `infrastructure/scripts/deploy-sandbox.sh` | `infrastructure/scripts/deploy-sandbox.sh` |
| `infrastructure/database/scripts/bootstrap-db-user.sh` | `infrastructure/database/scripts/bootstrap-db-user.sh` |
| `infrastructure/database/scripts/run-sql.sh` | `infrastructure/database/scripts/run-sql.sh` |

New Quantic files: `lib/config.ts`, `lib/deploy-guard.ts`, `lib/constructs/agent-runtime-role.ts`, `scripts/check-deploy-target.ts`, `database/migrations/001_vector.sql`, `002_hr_schema.sql`, `003_runtime_db_role.sql`, tests, `.github/workflows/infrastructure.yml`, `.env.example`, `.gitignore`. No Café Fausse repository files were edited.

## Network and MCP decision

AgentCore in VPC mode puts elastic network interfaces in our subnets. Invocations still arrive at the public AgentCore endpoint; the VPC path is outbound only. Aurora stays on isolated subnets. TCP 5432 is allowed only from the runtime security group and the SSM admin host. The runtime security group has no inbound rule.

One NAT gateway is the Bedrock path. AWS says a public subnet does not give those interfaces internet access, and a runtime with no internet needs ECR, S3, and CloudWatch Logs endpoints before it can start. Bedrock would be another interface endpoint. That set is about $58 per month in two zones before data, versus about $33 per month for one NAT plus data. NAT is the smaller path and the one the AgentCore VPC sample uses. Interface endpoints remain the fallback if this NAT is rejected before deploy. The template contains the NAT. It is not created until deploy.

MCP stays inside the same runtime package and uses stdio between LangGraph and the tool process. AgentCore's native MCP protocol is streamable HTTP and would make the tool server its own runtime. Stdio keeps a single host and skips Gateway. Container packaging is the fallback if a later runtime shows that direct code deploy cannot spawn the stdio child. That check needs a live runtime, so it is not done.

`cdk.context.json` pins `us-east-2a` and `us-east-2b` so synthesis does not call AWS. Those names still have to be shown to be `use2-az1` and `use2-az2` before deploy. The account-specific mapping was not looked up in this step.

## Synth and tests

Commands, from `infrastructure/`, with no AWS credentials and lookups disabled:

- `npm test` — 12 tests passed
- `npm run build` — `tsc --noEmit` passed
- `npm run synth` — `QuanticHrAgentStack` synthesized

The template contains one new VPC (`10.20.0.0/16`), one NAT gateway, six subnets, one Aurora PostgreSQL 17.4 Serverless v2 cluster (0.5–2 ACU, encrypted, IAM auth, deletion protection, database `quantic_hr`), secret `quantic-hr-agent/dev/database/admin`, one `t4g.nano` admin host, and role `quantic-hr-agent-dev-runtime`. The role may invoke the Titan embedding model, the Claude Sonnet 4.5 inference profile, and that foundation model in `us-east-1`, `us-east-2`, and `us-west-2`. It may call `rds-db:connect` only as `quantic_hr_agent`. It may write one log group. It has no Secrets Manager permissions. The template has no Café Fausse or AEA names.

Migrations were not executed. `cdk diff` and the deploy script were not run.

## Safe deploy, after a separate approval

1. Confirm `us-east-2a` and `us-east-2b` are `use2-az1` and `use2-az2`. Stop if they are not.
2. Run `infrastructure/scripts/validate-aws-env.sh`. It must show account `287238357427`, region `us-east-2`, and stack `QuanticHrAgentStack`.
3. Run `infrastructure/scripts/deploy-sandbox.sh` only if this change set is accepted. It refuses `CafeFausseApplicationStack` and `AeaSandboxStack`, prints the stack, database, and secret name, and deploys only after the stack name and the word `deploy` are typed.
4. Do not start the cluster until the first session is a read-only `SELECT` on `pg_available_extensions`. Then apply `001_vector.sql`, `002_hr_schema.sql`, and `003_runtime_db_role.sql`.
5. CDKToolkit is already present. Do not bootstrap again.

Estimated cost if the stack is left up: NAT about $33 per month plus data and a public IPv4 address, Aurora about $44 per month at the 0.5 ACU floor while running, and the admin host a few dollars while running. Stopping Aurora and the host does not stop the NAT charge. Bedrock is extra and was not invoked. Rejecting the NAT before deploy avoids that charge.

## Schedule

G1 (Oct 24) still needs frozen API and MCP contracts plus representative synthetic rows. This step supplies the schema and the stack, not those contracts. G2 (Oct 30) still depends on a live `vector` extension, which waits on deploy approval. Fixture retrieval can proceed before that. This step does not move the November 15 date if the deploy decision is made this week.

## Still unverified without a later approval

- Account-local AZ IDs for `us-east-2a` and `us-east-2b`
- `CREATE EXTENSION vector` on engine 17.4
- A real Bedrock invoke, including whether the cross-region profile needs more model ARNs than the three US regions in the role
- Stdio child-process support on AgentCore direct code deploy
- End-to-end private connectivity from a real runtime ENI
