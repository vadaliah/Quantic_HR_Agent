# Quantic HR Agent — Lean Master Plan

**Deadline: November 15, 2026.** Three-person team. Target: Quantic rubric score 5, with no unnecessary platform scope.

**Governing delivery path:** [COST_FIRST_DELIVERY_STRATEGY.md](COST_FIRST_DELIVERY_STRATEGY.md). Do not provision billable AWS resources. Implement the same architecture locally first.

## Core architecture
Vite React UI + FastAPI BFF (/chat, /health) → AWS Bedrock AgentCore (LangGraph orchestrator) → real MCP client/server tools → Aurora Serverless v2 PostgreSQL + pgvector (policy RAG and synthetic HR records). Bedrock for chat and embeddings. Retain Render for UI/BFF unless a simpler fully automated deployment is justified and approved.

Reuse the AWS CDK TypeScript infrastructure patterns in [Café Fausse](https://github.com/vadaliah/Quantic_Cafe_Fausse_Application); provision an **independent Quantic stack**. Never share Café Fausse application records, secrets, or operational database resources.

## Minimum grading scope
- Two complete workflows: **remote-work eligibility** and **PTO guidance**.
- At least five real MCP tools, initially target six: `search_policy_documents`, `get_policy_section`, `lookup_employee_profile`, `check_pto_balance`, `check_policy_compliance`, `draft_hr_email`. Add optional tools only if essential to demos.
- Policy corpus: 5–20 documents, approximately 30–120 pages, at least two document formats; cited multi-document RAG and out-of-corpus guardrails.
- Synthetic employee, PTO, manager, policy/location data; explicit approval for mock actions; no irreversible live HR changes.
- Trace shows tool names, arguments, summarized outputs, citations, and final answer basis—not hidden chain-of-thought.
- CI on push/PR with startup/build and MCP discovery/call tests; deployments gated on passing tests.
- Evaluation: 20–30 gold cases, groundedness, citation accuracy, tool selection, workflow completion, escalation/clarification, safety, p50/p95 latency over 10–20 tasks, and one ablation.
- Local development path and public deployed URL. Required README, design-and-evaluation.md, ai-tooling.md, deployed.md, evaluation artifacts. Share repository with `quantic-grader`; 7–10 minute recorded video with two agentic demos and required participant/ID instructions.

## Scope exclusions until submission
No multi-agent architecture, AgentCore Gateway unless required, enterprise HR authentication, Kubernetes, production monitoring platform, general-purpose multi-project CDK library, or full hosting migration. Use minimal chat session state only if clarification flows require it.

## Ownership
- **A (Infra/Data):** Café Fausse CDK reuse, independent Aurora, private networking, IAM, pgvector, ingestion, AgentCore deployment.
- **B (Agent/MCP):** tool schemas/server, LangGraph orchestration, Bedrock, deterministic compliance, safety and traces.
- **C (App/Quality):** React, FastAPI, Render automation, CI, evaluation, docs/demo.

## High-level Gantt (calendar blocks)
| Stream | Oct 20–23 | Oct 24–27 | Oct 28–31 | Nov 1–4 | Nov 5–8 | Nov 9–11 | Nov 12–14 | Nov 15 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| CDK audit, contracts | ■ | | | | | | | |
| Quantic infrastructure / Aurora | ■ | ■ | ■ | | | | | |
| Policy corpus / pgvector RAG | ■ | ■ | ■ | | | | | |
| MCP tools / compliance | | ■ | ■ | ■ | | | | |
| Agent and demo workflows | | | ■ | ■ | ■ | | | |
| BFF, UI and deployment automation | | ■ | ■ | ■ | ■ | | | |
| CI, contracts and smoke tests | ■ | ■ | ■ | ■ | ■ | ■ | | |
| Evaluations and ablation | | | ■ | ■ | ■ | ■ | ■ | |
| Final integration, docs and video | | | | | ■ | ■ | ■ | |
| Submission | | | | | | | | ◆ |

## Go/no-go milestone dates
- **Oct 21:** G0 — read-only AWS inventory; identify CDK modules and resolve AgentCore-to-private-Aurora connectivity design.
- **Oct 24:** G1 — frozen API/MCP contracts and representative synthetic data.
- **Oct 30:** G2 — two-format policy ingestion and pgvector retrieval with correct citations.
- **Nov 4:** G3 — both workflows execute locally through actual MCP protocol.
- **Nov 8:** G4 — feature freeze; both demos operate in integrated UI.
- **Nov 11:** G5 — public URL verified end to end: Render → AgentCore → MCP → Aurora.
- **Nov 13:** G6 — reproducible evaluations, metric tables, ablation, final documentation.
- **Nov 14:** G7 — video recorded, grader access and submission package verified.
- **Nov 15:** final submission.

## Risks and contingencies
The critical path is AWS IAM/network and agent-to-private-Aurora access, AgentCore+MCP integration, correct grounded RAG, full-stack public deployment, then protected evaluation/demo time. Validate region/model and pgvector support early. If any milestone slips >1 working day, shrink UI, policies and tool count to rubric minimum; do **not** drop the two workflows, actual MCP protocol, citations, deployed app, CI or evaluation.

## Execution rule
Step 0: inspect both repositories, verify AWS status read-only, define exact Quantic-specific CDK changes and API contracts, scaffold minimal CI. Present the plan for approval **before provisioning, deploying, or modifying AWS resources**. Work incrementally and keep Café Fausse untouched.
