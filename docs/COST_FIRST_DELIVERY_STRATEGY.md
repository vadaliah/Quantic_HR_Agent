# Cost-first delivery decision — October 20, 2026

**Approved direction:** Free-tier/local-first; provision billable infrastructure only as late as practical, after application functionality and automated tests are ready. Protect the November 15 submission deadline. This decision **supersedes** conflicting provisioning instructions in `docs/MASTER_PLAN.md`, `docs/STEP1_INFRASTRUCTURE_IMPLEMENTATION.md`, and `docs/STEP1B_BASELINE_ENVIRONMENT.md`.

## Immediate hold — no billable AWS deployment

Do **NOT** deploy `QuanticHrAgentStack` as currently synthesized: it includes a continuously billed NAT/EIP, Aurora Serverless v2 and associated resources. Do not start existing stopped Café Fausse/AEA Aurora clusters, create new clusters, NAT gateways, VPC endpoints, EC2 hosts, paid external services, or invoke paid inference without explicit separate authorization. Preserve the work on `feature/step1-infrastructure`; do not delete it or modify existing projects.

The desired **baseline now** is a reproducible **local and CI application environment**, not a permanently deployed AWS foundation. It should include a working thin app/API shell and locally callable agent/MCP contract, using free/open-source components and synthetic fixtures. The essential grader-facing deployed URL is still required later.

## Default architecture for development and demo
- Local Python environment and Vite/React; FastAPI `/chat`, `/health` with operational MCP trace/citations contracts.
- Real MCP protocol, initially local stdio server/client or another documented compatible local transport.
- RAG: local FAISS or SQLite-backed index, local/free embedding model, deterministic document ingestion; data: versioned synthetic JSON/SQLite. No Aurora requirement for grading.
- LangGraph orchestration locally; configurable LLM provider adapter. Use an eligible genuinely free API allocation or local model where practical, with mocked LLM responses for CI. Keep Bedrock and AgentCore adapters/configuration available but don't pay to test them yet.
- Hosting: assess current **actual** no-cost quotas/eligibility for Render, Railway or equivalent. Do not assert free access based on outdated plan information. Prefer single-service deployment where possible to avoid multiple hosting bills.
- Existing optional CDK/Aurora/AgentCore stack stays in the repo as a future production-like variant; it is NOT the default path for this assignment.

## Cost gates
1. **Now → working local product:** offline/unit tests; policy documents, RAG, MCP, agent, UI, evaluation fixtures and scripts. No live chargeable service.
2. **Predeployment:** verify free-tier eligibility, terms, sleep/cold-start behavior, CI costs, persistence limits, and shareable URL. Identify unavoidable charges in dollars with assumptions and an upper-bound budget. Set billing alerts if AWS usage is approved (alerts do not enforce a hard cap).
3. **Only after local acceptance:** obtain explicit approval for any metered model invocation, AgentCore runtime, storage, Aurora/NAT, paid hosting or other resources. Provision the **smallest** permitted resources just before integrated demo and evaluation; tear down/stop afterwards only with explicit approval and awareness of residual charges.
4. **Final integration/demo:** deploy a compliant shareable application, demonstrate two real MCP tool-driven HR workflows and citations, measure evaluation outcomes, then document deployment and costs.

## Milestone adjustments (deadline unchanged)
- Oct 20–24: freeze local architecture/contracts, fixtures, CI skeleton, establish true local MCP client/server call.
- Oct 25–30: corpus, local RAG retrieval and citations; synthetic HR data.
- Oct 31–Nov 4: two local agent workflows; clarify/confirm/guardrails; UI/API.
- Nov 5–8: integrated local product feature freeze and evaluation suite.
- Nov 9–11: free-tier deployment + publicly accessible demos; paid components only with separate approval if unavoidable.
- Nov 12–14: evaluation, recording, documentation, grader access.
- Nov 15: submission.

## Cursor next actions (no provision)
1. Read this file **before** other step documents and report any conflicting assumptions.
2. Create a lean architecture delta (keep/adapt/defer) and exact local execution commands.
3. Make existing CDK stack an opt-in path, never run deploy scripts as part of default setup or CI.
4. Begin next **approved** application increment only after local contracts are clear; do not wait for AWS resources.
5. Commit/push all reviewed changes to a feature branch automatically; provide tests/branch/commit and stop before merging or external paid actions.

**Important:** "Zero fixed AWS infrastructure cost" does not imply zero total cost: GitHub, hosting and AI providers have eligibility/quotas and may meter usage. Verify rather than assume.
