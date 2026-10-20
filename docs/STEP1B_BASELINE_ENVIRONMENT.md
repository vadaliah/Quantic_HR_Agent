# Step 1B — Reusable AWS baseline and AgentCore Hello World

**Status:** Implement code, local tests, and read-only pre-deployment checks. **Do not provision AWS until the change set is approved.** Deadline remains November 15, 2026.

Read `docs/MASTER_PLAN.md`, `docs/INFRASTRUCTURE_REUSE.md`, `.cursor/rules/quantic-project.mdc`, and `docs/STEP1_IMPLEMENTATION_RESULTS.md` first.

## Outcome

Complete the independent Quantic AWS baseline so a reviewer can approve a single stack deploy:

- Aurora PostgreSQL Serverless v2, isolated networking, IAM, and guarded deployment automation from Step 1
- A **minimal AgentCore Hello World runtime** on the same VPC path the later HR agent will use

This is **not** RAG, MCP business tools, LangGraph orchestration, FastAPI, Vite, Render, synthetic HR seeding, or either demo workflow.

## Boundaries

- Work only in `vadaliah/Quantic_HR_Agent`. Do not modify Café Fausse or AEA resources, secrets, or stacks.
- Preserve CDK TypeScript, Aurora PostgreSQL/pgvector, Bedrock, AgentCore, later LangGraph/MCP, FastAPI, Vite React, and Render as the BFF/UI host.
- Do not implement `search_policy_documents`, other MCP tools, embeddings, corpus ingest, or HR application APIs.
- Do not generalize into a multi-project IaC library.
- `cdk synth` and tests must stay local/offline. `cdk diff` and identity/AZ checks may call AWS read-only. No `cdk deploy`, no cluster start, no Bedrock invoke, no `CREATE EXTENSION`, no NAT creation until approval.

## Tasks

1. Keep the isolated `QuanticHrAgentStack` (VPC `10.20.0.0/16`, one NAT, private AgentCore subnets, isolated Aurora, SSM admin host, runtime role).
2. Add a Hello World AgentCore runtime: HTTP `/ping` and `/invocations` only; echo the prompt; no model call; no database call; no MCP server.
3. Place that runtime in VPC mode on the existing private subnets and runtime security group. Invocations stay on the public AgentCore endpoint.
4. Wire deployment automation so the pre-deploy script proves account `287238357427`, region `us-east-2`, stack `QuanticHrAgentStack`, and AgentCore AZ IDs `use2-az1` / `use2-az2` before anyone can type `deploy`.
5. Run pre-deployment checks, write results, **stop for approval**. Commit and push the feature branch. Do not merge. Do not deploy.

## Acceptance / stop gate

Pass when synth/tests are green, the template contains the Hello World runtime plus the Step 1 baseline, Café/AEA names are absent, pre-deploy checks are read-only, and a reviewer can inspect the exact AWS change set.

**Stop.** No provisioning without an explicit yes on that change set.
