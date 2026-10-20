# Deferred — Application development (NOT AUTHORIZED YET)

**Status (October 20, 2026):** The user clarified that application/RAG/MCP business implementations must wait until the group reviews the business requirements. This document is retained only as a deferred idea list. **Do not execute this work now.**

## Current priority: infrastructure readiness only

Prepare a reproducible, documented, group-ready *infrastructure foundation*, without implementing business functionality and without changing AWS resources yet:

1. Preserve the already implemented Quantic AWS CDK constructs and the separate minimal AgentCore Hello World runtime. Review them for deploy readiness, but keep the deploy guard active.
2. Preserve locally runnable PostgreSQL/pgvector, basic Python/TypeScript dependencies, CI and minimal /health or Hello World smoke scaffolding as infrastructure diagnostics. Do not develop new HR schema, RAG, embeddings, agent reasoning, or MCP business tools. Already committed prototype files can remain on draft branches; do not treat them as approved requirements.
3. Confirm configurable connection parameters/secret handling, bootstrap scripts, reproducible install/test commands, runtime IAM/network assumptions, CI checks, and the deployment rollback/cleanup approach.
4. Maintain a cost inventory and identify the smallest shared AWS topology. In particular, assess reuse of the Café Fausse Aurora cluster rather than deploying the duplicate Quantic Aurora/NAT stack.
5. Document networking requirements for a shared group-accessible service, and distinguish *deployment-ready* from *deployed*. Do not assume a private Aurora cluster is reachable from a public service without an approved connectivity path.
6. Prepare a short infrastructure readiness checklist with blockers and an AWS provisioning plan for later user approval.

## Restrictions
- No Café Fausse snapshot, startup, modifications, database deletion or cluster deletion. The user deferred this decision until evening.
- No AWS deploy, new billable resources, or live Bedrock/AgentCore invocation without explicit approval.
- No HR data model, RAG, tool/business logic or LangGraph feature development until business requirements review.
- No automatic merge; commit/push reviewed infrastructure-only documentation/configuration to feature branch.

## Next deliverable
`docs/INFRASTRUCTURE_READINESS.md`: completed components, evidence of offline checks, credentials/network blockers, shared access design options with incremental recurring costs, and a later approval checklist. Keep Nov 15 deadline.
