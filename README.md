# Quantic HR Agent

Agentic RAG + MCP project for Quantic AI Engineering Techniques and Architectures. **Submission: November 15, 2026.**

## Start here
- [Lean master plan and Gantt milestones](docs/MASTER_PLAN.md)
- [Café Fausse CDK infrastructure reuse assessment](docs/INFRASTRUCTURE_REUSE.md)
- [Cursor project instructions](.cursor/rules/quantic-project.mdc)

Planned architecture: Vite React + FastAPI → Bedrock AgentCore/LangGraph → actual MCP tools → Aurora PostgreSQL/pgvector + Bedrock. Initial workflows are remote-work eligibility and PTO guidance.

**Current status:** Step 1 CDK code is local only. `infrastructure/` synthesizes `QuanticHrAgentStack` and does not deploy it. See [infrastructure/README.md](infrastructure/README.md) and [docs/STEP1_IMPLEMENTATION_RESULTS.md](docs/STEP1_IMPLEMENTATION_RESULTS.md). Café Fausse and AEA resources stay untouched.
