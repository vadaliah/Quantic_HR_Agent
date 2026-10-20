# Step 1B — Complete infrastructure baseline FIRST (October 20)

**Goal:** Finish a reproducible, working AWS infrastructure baseline this morning, before RAG, mock HR data, MCP business tools or any application-specific development. This changes the immediate execution order in MASTER_PLAN.md.

## Explicitly IN scope
- Review and integrate existing `feature/step1-infrastructure` CDK work into `main` via PR after checks; do not overwrite existing commits.
- New project-isolated `QuanticHrAgentStack` based on Café Fausse CDK; VPC/subnets/security groups/necessary egress, Aurora Serverless v2, database access/admin path, IAM, secrets, baseline logs.
- Automate deployment of a minimal AgentCore **hello-world** runtime and its invocation. No LangGraph or HR tools required yet. Include a tiny deterministic response and a runtime connectivity health probe as appropriate.
- Validate minimal Bedrock access with a low-cost invocation if deployment is authorized.
- Test private Aurora connectivity from the actual runtime (or a same-network test workload). Do not confuse network reachability with successful IAM DB auth; report both. Do not start or install pgvector just to prove infrastructure unless an approved connectivity smoke test requires it.
- Add project-specific `validate`, `synth/diff`, `deploy`, `status/verify` scripts, and documentation with outputs, URLs/ARNs, IAM and cost notes. Automate backend infrastructure and baseline deployment end to end; frontend application hosting can be scaffolded, but a production React UI is NOT required for baseline.

## OUT of scope until baseline accepted
- Policy corpus, chunking/indexing, embeddings pipeline, pgvector schema migration, synthetic HR records, HR business rules, RAG.
- LangGraph workflows, remote-work/PTO tasks, application MCP tools, chat UI, application-specific API.
- Multi-project CDK refactor, Gateway, Kubernetes, advanced telemetry.

## Gate A: predeployment (no AWS writes)
1. Confirm expected AWS account/region and mapped AZ IDs, AgentCore network settings, runtime packaging and transport.
2. Run build/tests/synth and read-only CDK diff. Show precise stack resources and monthly cost assumptions, especially NAT/Aurora.
3. Confirm that existing Café Fausse and AEA stacks are untouched.
4. Obtain explicit user approval of the change set **before** provisioning. The intention to finish this morning is not authorization to bypass this safety gate.

## Gate B: after explicit deployment authorization
1. Deploy Quantic-only infrastructure via guarded scripts.
2. Deploy hello-world AgentCore runtime with documented, repeatable automation.
3. Run end-to-end checks: VPC/Aurora status; test PostgreSQL reachability and IAM auth; minimal Bedrock invocation; invoke hello-world runtime; health verification and logging.
4. Report pass/fail with evidence. If blocked, stop and report exact blocker, without altering other stacks.
5. Commit all scripts and docs; push branch automatically for review, no manual user Git commands.

## Exit criteria
- All baseline AWS infrastructure and runtime deployed, reachable and verifiable.
- One-command or well-documented repeatable deploy/verify procedure.
- No HR business functions included.
- Independent Quantic resources and no impact on existing stacks.
- `docs/BASELINE_DEPLOYMENT_RESULTS.md` includes state, tested commands, actual results, costs, known issues, and readiness to start application development.

**Execute Gate A immediately. Do not deploy until explicit change-set approval.** Follow automatic feature-branch push instructions in `.cursor/rules/quantic-project.mdc`.
