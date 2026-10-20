# Architecture decision — retain Aurora (October 20, 2026)

**Current user decision:** Continue on the original Aurora PostgreSQL path for the Quantic group project. Do not substitute a local-only SQLite/FAISS architecture or migrate to a different hosted database without a new decision.

## Architecture
- Independent Quantic AWS CDK stack: isolated networking, Aurora PostgreSQL Serverless v2 with pgvector, IAM/secrets/security groups.
- Bedrock and AgentCore architecture preserved; LangGraph orchestrator and genuine MCP client/server integration.
- Vite React/FastAPI shared web application, expected on Render unless a different host is approved.
- All three group members use GitHub for source control and the deployed application over a shareable URL. Controlled developer/database access must be documented; do not publish Aurora directly to the internet.
- Synthetic HR data and document embeddings live in Aurora when integration begins. Local unit tests/fixtures are still encouraged for speed and avoiding unnecessary API usage, **but Aurora remains the target database**.

## Cost and approval
- Earlier `docs/COST_FIRST_DELIVERY_STRATEGY.md` preferred local SQLite/FAISS; **that architecture substitution is superseded by this decision**.
- Cost discipline remains: avoid unnecessary resource duplication, use free tiers where they do not compromise the agreed Aurora design, and avoid leaving resources running idle where practical.
- An independent Aurora cluster, NAT/EIP, and related AWS resources may incur charges even with low usage. Do not claim a zero-cost solution.
- **Creating billable resources still requires explicit user approval of the change set and approximate monthly cost.** Existing prior approval covers a reviewed CDK diff in principle; verify it remains current and predeploy checks pass before any cloud action. Do not modify Café Fausse/AEA resources.
- Preserve the original Step 1/1B CDK implementation and finish the baseline before RAG/HR-specific development unless the user changes direction.

## Immediate engineering priority
1. Confirm Step 1B feature branch and reconcile with main; preserve commits.
2. Restore the established AWS profile, rerun predeploy identity/AZ verification and inspect CDK diff.
3. Present any updated resource/cost differences for approval (no silent AWS deploy).
4. Following approval, deploy and smoke-test Quantic VPC/Aurora and minimal AgentCore Hello World, documenting results and shared access model.
5. Only then begin application-specific schema, RAG, MCP tools and workflows.

## Precedence
This is the latest architecture decision; it supersedes conflicting local-only database recommendations in the cost-first document and Cursor rules. It **does not** waive the explicit cost/deployment approval gate.
