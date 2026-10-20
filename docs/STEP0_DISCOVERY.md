# Step 0 — Infrastructure discovery and execution handoff

**Status:** Repository source inventory completed October 19, 2026; live AWS verification and local Cursor review **pending**. This is not approval to provision.

## Confirmed source assets in Café Fausse
- `infrastructure/bin/infrastructure.ts`: creates `CafeFausseApplicationStack`.
- `infrastructure/lib/infrastructure-stack.ts`: composes Network, Database, DatabaseAccess.
- `infrastructure/lib/constructs/network.ts`: isolated-subnet VPC with SSM endpoints and no NAT.
- `infrastructure/lib/constructs/database.ts`: PostgreSQL 17.4 Aurora Serverless v2 (0.5–2 ACU), generated secret, IAM auth, isolated subnets.
- `infrastructure/lib/constructs/database-access.ts`: SSM-managed EC2 access host.
- `infrastructure/scripts/{validate-aws-env,bootstrap-aws,synth-infra,deploy-sandbox}.sh`: existing account validation/CDK build/diff/deploy patterns.
- `infrastructure/database/scripts/{bootstrap-db-user,run-sql}.sh`: database setup and SSM-tunneled SQL execution.
- `frontend/`: Vite React conventions, **not** deploy hosting infrastructure.

## Provisional reuse matrix
| Reuse unchanged concept | Adapt | New minimal Quantic work | Defer |
|---|---|---|---|
| AWS CDK TypeScript, CDK synth/diff pattern | Stack naming, account/profile/region/project config | Quantic-specific CDK stack and isolated DB/secret | General multi-project framework |
| Aurora IAM/database pattern | Networking and security group boundaries | pgvector extension, schema, migrations, test fixtures | Complex production database operations |
| SSM database administration | App-runtime database connection path | Bedrock/AgentCore/MCP runtime integration | AgentCore Gateway unless essential |
| Vite React conventions | Build and deployment variables | FastAPI/React hosting automation + GitHub Actions gates | Hosting migration without approval |

## Key blocker to resolve first
The Café Fausse VPC has private-isolated subnets. An SSM port-forwarding tunnel used for local administration is **not a deployed application DB connectivity design**. Confirm where MCP actually runs and how it reaches Aurora privately. Verify AgentCore runtime, model/embedding availability and `vector` extension permissions for the proposed AWS region before implementing.

## Cursor local task: execute read-only discovery only
1. Open the Quantic repository as Cursor workspace. Read `docs/MASTER_PLAN.md`, `docs/INFRASTRUCTURE_REUSE.md` and this file.
2. Find a local checkout of `vadaliah/Quantic_Cafe_Fausse_Application`, or inspect it through GitHub. Verify source file paths and avoid altering it.
3. Using preconfigured AWS credentials, run read-only identity, CloudFormation, RDS, VPC, IAM policy inspection and Bedrock/AgentCore availability checks. Do not print secrets or tokens. **No provisioning or deployment.** Do not assume the expected account ID in Café Fausse scripts is valid for Quantic.
4. Produce `docs/STEP0_AWS_FINDINGS.md` identifying: account/region (masked as appropriate), existing stacks, Aurora state, pgvector status (if DB read-only access allows), required private DB connectivity, actual MCP deployment mechanism, and candidate host automation.
5. Propose a small CDK change list with files, owner, estimated person-days, schedule impact and test/exit gate. Clearly mark unverified items.
6. Identify any Quantic grading risks: runnable local stack, actual MCP protocol (>=5 tools), citation-grounded RAG, dual multi-step demos, public URL, CI checks, evaluation.
7. Stop and request approval; no IAM changes, stack creation, database writes, expensive API calls, or destructive operations.

## Gate G0 acceptance by October 21
- Confirmed reuse/adapt/build/defer list and existing live AWS inventory.
- Resolved or risk-tracked AgentCore/MCP-to-Aurora networking and permissions design.
- Confirmed whether Render deployment scripts exist elsewhere.
- Minimal implementation proposal that meets November 15 milestones without optional infrastructure refactoring.
