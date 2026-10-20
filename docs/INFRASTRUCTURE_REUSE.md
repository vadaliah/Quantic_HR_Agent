# Café Fausse → Quantic infrastructure reuse assessment

Source: [Quantic_Cafe_Fausse_Application](https://github.com/vadaliah/Quantic_Cafe_Fausse_Application), inspected on main October 19, 2026. **Repository review only:** no live AWS resources, pgvector extension, model access, or runtime connectivity have been verified.

## Reusable existing components

| Café Fausse asset | Location | Recommendation |
|---|---|---|
| AWS CDK TypeScript | `infrastructure/bin/infrastructure.ts`, `infrastructure/lib/infrastructure-stack.ts` | Reuse CDK patterns; new Quantic stack identity |
| Isolated VPC, SSM endpoints | `infrastructure/lib/constructs/network.ts` | Parameterize networking for an independent Quantic environment |
| Aurora PostgreSQL Serverless v2, IAM auth, generated secret | `infrastructure/lib/constructs/database.ts` | New Quantic cluster/DB/secret; check pgvector support |
| SSM-access EC2 instance | `infrastructure/lib/constructs/database-access.ts` | Reuse secure administration pattern if needed |
| Environment, CDK and deployment scripts | `infrastructure/scripts/bootstrap-aws.sh`, `validate-aws-env.sh`, `synth-infra.sh`, `deploy-sandbox.sh` | Adapt account, AWS profile, region, naming, safety checks |
| Database bootstrap and SSM tunnel | `infrastructure/database/scripts/bootstrap-db-user.sh`, `run-sql.sh` | Adapt for independent Quantic users/schemas and SQL |
| React/Vite tooling | `frontend/` | Reuse build conventions, not Café Fausse business UI |

The current CDK stack is named `CafeFausseApplicationStack`. Its Aurora construct uses PostgreSQL 17.4, serverless min 0.5/max 2 ACU, private-isolated subnets, IAM authentication and a generated credential secret. Scripts include Café Fausse-specific profiles, database/stack names and an expected account: **do not copy these values blindly**.

The deployed network has no NAT gateway and includes SSM-related endpoints. Do not assume that new workloads can access Bedrock/Secrets Manager over this network or access Aurora from AgentCore; design and validate the actual connection path early. The SSM tunnel is appropriate for administrator access, not the running agent's DB connectivity.

## What remains to build or verify

- Parameterized, project-isolated Quantic CDK deployment with new stack, DB, VPC/networking where needed, IAM, secrets and tags.
- AgentCore deployment and **real** MCP server execution; choose actual runtime/process boundaries and transport.
- Bedrock chat/embeddings permissions, region support and provider configuration.
- Aurora `vector` extension availability, migrations and idempotent synthetic HR seed data.
- Private Aurora access from Quantic MCP service; security group/IAM and networking tests.
- API hosting and frontend deployment automation; Render remains the agreed baseline until alternate hosting is approved.
- GitHub Actions build/test/deployment gates and deployed smoke tests.
- Secrets handling, endpoint publishing, safe deployment diff, and limited project-specific teardown.

No CDK resources for React frontend hosting, FastAPI deployment, AgentCore or MCP runtime were observed in the inspected Café Fausse repository. Other local repositories or external deploy systems may contain reusable scripts: verify before building replacements.

## Reuse-first implementation constraints

1. Never alter or destroy existing Café Fausse resources. Clone **infrastructure patterns**, not live app state, data or secrets.
2. Reuse AWS CDK TypeScript; do not introduce Terraform or a second IaC system for this project.
3. Prefer project-scoped configuration such as `project=quantic-hr-agent` and `env=dev`; separate names, secret paths, roles, security controls and database resources.
4. Keep deploy/teardown reviewed and confirmation-gated; verify expected AWS account/region. Destructive workflows need additional explicit approval.
5. Do not generalize all CDK components into a universal multi-project framework before November 15.
6. Build a small predictable `validate → synth/diff → deploy → migrate/seed → app deploy → health/smoke` flow.
7. Do not treat mocked AWS tests as proof that deployed MCP and RAG networking works.

## First checkpoint (read-only, before deployment)

- Confirm AWS account, region, existing stacks, Aurora state, capabilities and permissions.
- Produce `reuse unchanged / adapt / build / defer` inventory with exact file paths.
- Verify pgvector and selected Bedrock model availability.
- Document AgentCore ↔ MCP ↔ Aurora network/auth architecture.
- Confirm existing CI/CD and frontend automation in other repositories if relevant.
- Report minimal Quantic-only CDK edits, effort and Nov 15 schedule risk.
- Request explicit approval before provisioning or changing paid AWS infrastructure.

## Success criteria

An independent Quantic deployment with synthetic data runs two agentic HR workflows through real MCP calls and cited RAG. Infrastructure and application deployment are repeatable, AWS costs/resource boundaries are documented, and the public UI and health endpoint work without a grader needing AWS credentials.
