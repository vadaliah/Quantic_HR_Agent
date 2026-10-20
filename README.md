# Quantic HR Agent

Agentic RAG + MCP project for Quantic AI Engineering Techniques and Architectures. **Submission: November 15, 2026.**

## Start here
- [Lean master plan and Gantt milestones](docs/MASTER_PLAN.md)
- [Café Fausse CDK infrastructure reuse assessment](docs/INFRASTRUCTURE_REUSE.md)
- [Cursor project instructions](.cursor/rules/quantic-project.mdc)

Planned architecture: Vite React + FastAPI → Bedrock AgentCore/LangGraph → actual MCP tools → Aurora PostgreSQL/pgvector + Bedrock. Initial workflows are remote-work eligibility and PTO guidance.

**Current status:** Step 1B code is local only. `infrastructure/` synthesizes `QuanticHrAgentStack` with Aurora, networking, IAM, and an AgentCore Hello World runtime. Nothing is deployed until the pre-deploy change set is approved. See [docs/STEP1B_BASELINE_ENVIRONMENT.md](docs/STEP1B_BASELINE_ENVIRONMENT.md). Café Fausse and AEA resources stay untouched.
