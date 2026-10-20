# Cost-first delivery strategy

**Status:** Governing development strategy from 20 Oct 2026 until an explicit paid-infra approval. Deadline remains **15 November 2026**. Rubric target 5.

This document overrides any earlier instruction to provision Aurora, NAT, AgentCore, or Bedrock as a prerequisite for feature work.

## Rule

Ship the graded agentic HR system on a **local, free/open-source path first**. Keep the existing AWS CDK as the future production shape. **Do not create billable AWS resources.**

Blocked without a new written approval: `cdk deploy`, `deploy-sandbox.sh`, starting Aurora, creating NAT, invoking Bedrock, creating IAM roles in AWS, AgentCore create/update, and any other paid control-plane change.

Allowed: local Postgres/pgvector, local MCP, LangGraph, FastAPI, Vite, unit/CI tests, `cdk synth` / `cdk test` with `--lookups false`.

## Architecture (unchanged contracts, local runtime)

```text
Vite React (local / later Render)
  → FastAPI BFF /chat /health
    → LangGraph agent (local process)
      → real MCP client/server (stdio for local and tests)
        → PostgreSQL + pgvector (local Homebrew or CI service)
```

AWS mapping later, not now:

| Local now | CDK later (not deployed) |
|---|---|
| Postgres + pgvector | Aurora Serverless v2 |
| LangGraph process | AgentCore runtime |
| stdio MCP | stdio MCP inside the runtime |
| lexical/local embeddings | Bedrock Titan embeddings |
| rule planner or optional local LLM | Bedrock Claude |

Do not drop: two workflows (remote-work eligibility, PTO guidance), real MCP protocol, citations, tool traces, CI, evaluation, public URL before submission.

## Incremental sequence (cost-first)

1. **This step — local spine.** Local database, synthetic data, six MCP tools over the real MCP wire, LangGraph loop, FastAPI contracts, Vite shell, CI without AWS. CDK remains synth-only.
2. **Grounded retrieval.** Heading-aware chunks, local embeddings or lexical+pgvector, citation goldens. Still no AWS.
3. **Workflow quality.** Both demos complete through MCP; guardrails; 20–30 eval cases; one ablation.
4. **Shareable app.** FastAPI + Vite on Render (or approved free host). BFF talks to the local/agent process or a free runtime, not a paid AWS data plane, until costs are accepted.
5. **Optional AWS cutover.** Only after written approval of the NAT/Aurora/AgentCore bill. Then `QUANTIC_ALLOW_AWS_DEPLOY=yes` unlocks `deploy-sandbox.sh`.

## Non-goals until paid approval

NAT gateway, Aurora cluster, AgentCore Hello World in AWS, Bedrock invokes, SSM admin host, Secrets Manager beyond what already exists in other stacks.

Café Fausse and AEA stay untouched.

## Operator switch

Default deny:

```bash
# still blocked
infrastructure/scripts/deploy-sandbox.sh

# only after a later paid-infra approval
QUANTIC_ALLOW_AWS_DEPLOY=yes infrastructure/scripts/deploy-sandbox.sh
```
