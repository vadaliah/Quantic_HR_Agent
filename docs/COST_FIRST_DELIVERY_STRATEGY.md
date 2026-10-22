# Cost-first delivery decision — October 20, 2026

**Approved direction:** Free-tier/local-first; provision billable infrastructure only as late as practical, after application functionality and automated tests are ready. Protect the November 15 submission deadline. This decision **supersedes** conflicting provisioning instructions in `docs/MASTER_PLAN.md`, `docs/STEP1_INFRASTRUCTURE_IMPLEMENTATION.md`, and `docs/STEP1B_BASELINE_ENVIRONMENT.md`.

The reusable CDK on this branch remains the production shape (create-new Aurora **or** read-only Café Fausse reuse). It is **not** the default path for daily work.

## Immediate hold — no billable AWS deployment

Do **NOT** deploy `QuanticHrAgentStack` as currently synthesized: both database modes still include a continuously billed NAT/EIP and AgentCore Hello World. Do not start existing stopped Café Fausse/AEA Aurora clusters, create new clusters, NAT gateways, VPC endpoints, EC2 hosts, paid external services, or invoke paid inference without explicit separate authorization.

The desired **baseline now** is a reproducible **local and CI application environment**, not a permanently deployed AWS foundation.

## Operator switch

Default deny:

```bash
infrastructure/scripts/deploy-sandbox.sh

# only after a later paid-infra approval
QUANTIC_ALLOW_AWS_DEPLOY=yes infrastructure/scripts/deploy-sandbox.sh
```

Allowed without that flag: local Postgres/pgvector, local MCP, LangGraph, FastAPI, Vite, unit/CI tests, `cdk synth` / `npm test` with `--lookups false`.

## Default architecture for development and demo
- Local Python environment and Vite/React; FastAPI `/chat`, `/health` with operational MCP trace/citations contracts.
- Real MCP protocol, initially local stdio server/client.
- LangGraph orchestration locally; configurable LLM provider adapter. Keep Bedrock and AgentCore adapters available but do not pay to test them yet.
- Existing optional CDK/Aurora/AgentCore stack stays in the repo as a future production-like variant.

## Cost gates
1. **Now → working local product:** offline/unit tests; policy documents, RAG, MCP, agent, UI, evaluation fixtures and scripts. No live chargeable service.
2. **Predeployment:** verify free-tier eligibility and identify unavoidable charges. Set billing alerts if AWS usage is approved (alerts do not enforce a hard cap).
3. **Only after local acceptance:** obtain explicit approval, then set `QUANTIC_ALLOW_AWS_DEPLOY=yes` for the smallest permitted resources.
4. **Final integration/demo:** deploy a compliant shareable application, demonstrate two real MCP tool-driven HR workflows and citations.

Café Fausse and AEA stay untouched.
