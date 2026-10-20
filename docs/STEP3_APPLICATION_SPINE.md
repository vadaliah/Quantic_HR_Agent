# Step 3 — Application spine (October 20, 2026)

## Scope and approval
User deferred all Café Fausse snapshot/deletion/Aurora decisions until evening. **No AWS mutations** (including snapshots, starts, deletion, provisioning or deployment). Keep Aurora PostgreSQL as target database, with local PostgreSQL/pgvector for tests. Do not block app work on the database decision. Keep PR #1 in draft until reviewed.

## Increment 1 — RAG and robust conversational workflows
On `feature/cost-first-local-dev` (or fresh feature branch), prioritize:
1. Ingest the existing policy corpus into heading-aware sections with stable document/section IDs, source URIs and content hashes; build idempotent PostgreSQL/pgvector migrations and deterministic fixtures. Embeddings should use a genuine locally runnable model when practical, and permit deterministic fake embedding in CI. Include vector search, metadata filters, similarity diagnostics, citations and negative retrieval tests. Do not present ILIKE as semantic RAG.
2. Preserve the genuine MCP stdio protocol client/server, six tools and traceability. Add input validation, explicit errors, parameterized SQL, and safe policy-compliance semantics.
3. Build LLM-driven LangGraph planner/response synthesis behind an adapter for local/free model and eventual Bedrock; use mocked provider in automated tests. Do not conflate the existing keyword router with an AI-powered agent. Ensure no unapproved paid API invocation.
4. Implement two workflows: (a) remote-work eligibility with destination/region and policy checks; (b) PTO with user-requested duration (fix hardcoded 8-hour bug), remaining-balance checks, clarifying questions and no irreversible HR changes. Answer using structured MCP result + precise source citation; surface uncertainty and missing information.
5. Verify end-to-end `/chat`, `/health`, React UI, and representative good/edge/failure flows; test running from a clean checkout. Keep secrets out of source and CI.

## Deliverables
- Small, reviewable feature commits/PR(s), tests and test logs; auto-commit and push feature branch, no auto merge.
- Document how to run locally, how to change PostgreSQL `DATABASE_URL` to Aurora later, and any VPC/private networking blockers without changing AWS.
- A concise status summary showing which behaviors were tested live vs mocked, remaining blockers, and next increment.
- Avoid broad refactor or unnecessary infra deployment.

## Separate pending decision
Café Fausse snapshot and possible deletion **remain explicitly deferred**. If resumed, clarify whether deleting only `cafe_fausse_db` or the entire cluster; do not delete the cluster if it will be reused for Quantic.
