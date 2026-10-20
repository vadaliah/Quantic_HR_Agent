# Step 1 — Quantic infrastructure code (no deployment authorization)

**Status:** Approved to implement code and local/offline tests only. **Deadline:** November 15, 2026. Start after reading `docs/MASTER_PLAN.md`, `docs/INFRASTRUCTURE_REUSE.md`, and `docs/STEP0_AWS_FINDINGS.md`.

## Outcome
A small, independent Quantic AWS CDK TypeScript stack built from proven Café Fausse patterns, plus project-scoped configuration/scripts. It must synthesize and be reviewable without changing AWS. This is **not** permission to provision, deploy, start databases, create IAM resources, run charged Bedrock invocations, repair existing stacks, or run destructive operations.

## Boundaries and priorities
- Preserve existing Café Fausse and AEA environments exactly as they are.
- Work only within `vadaliah/Quantic_HR_Agent`; read/source Café Fausse code at `/Users/hirenvadalia/cafe-fausse-application` where available.
- Reuse **CDK TypeScript** approaches from Café Fausse, not project-specific account credentials, DB secrets, production data or restaurant logic.
- Do not generalize into a reusable multi-project infrastructure framework yet. Keep component contracts ready for future extraction, but prioritize Quantic.
- Retain Aurora PostgreSQL + pgvector, Bedrock, AgentCore, LangGraph/MCP, FastAPI and Vite React, and the current Render hosting baseline.

## Tasks

### 1. Scaffold and project configuration
- Add `infrastructure/` with an isolated CDK entrypoint and stack named `QuanticHrAgentStack`; use clear project/environment tags.
- Create config for AWS account/region/profile, project name, database name, secret path and resource naming. Never commit secrets or session credentials.
- Add `.env.example` or equivalent documenting required variables, and `.gitignore` for synthesized/build/secrets artifacts.
- Add `infrastructure/README.md` with prerequisites, validate/synth/diff commands, and safety guardrails.

### 2. Adapt Café Fausse constructs
- Copy/adapt only needed CDK constructs: VPC/subnets/security groups; Aurora PostgreSQL Serverless v2 (encrypted, generated administrative secret, IAM DB auth); optional database administration access pattern.
- New Quantic cluster, database `quantic_hr`, stack-scoped resource names, roles, secret path and tags. Never import or overwrite Café/AEA physical resources.
- Keep Aurora private and restrict inbound DB connections to the approved Quantic runtime security group(s).
- Add IAM execution-role policies scoped as tightly as feasible to the intended Bedrock model/inference profile, IAM DB auth, logs, and necessary runtime resources.
- Add migration files for `vector` extension and synthetic HR/RAG tables, but **do not execute** them against AWS at this stage.

### 3. Validate design before hard-coding NAT or MCP packaging
- Investigate AgentCore Runtime VPC networking, outbound Bedrock access, egress options, service endpoints, and agent invocation auth. Establish the supported route from deployed runtime to private Aurora.
- Verify whether **stdio MCP inside AgentCore Runtime** is supported for the planned LangGraph client and packaging. If feasible, implement this; otherwise recommend the smallest compatible MCP transport, and document why.
- Do not assume a NAT gateway is required or provision one until connectivity alternatives, cost and security are assessed.
- Record final proposed network topology and runtime/transport choice in a concise design note.
- Explicitly flag anything that cannot be verified without live deployment or paid calls.

### 4. Deployment scripts, offline validation, and safety
- Adapt existing account/region validation, TypeScript build, CDK synth/diff and guarded deploy script conventions.
- Scripts must require a project-specific target and display stack/resource names before deploy; block wrong account/region and existing Café/AEA stacks.
- Deployment scripts may be authored but **must not be executed** at this step.
- Prefer simple commands (e.g., `npm run build`, `npm run synth`, `npm test`) and small CDK assertions for resource isolation, encryption, IAM, and database ingress.
- `cdk synth` is allowed if entirely local/offline; `cdk diff` or lookup that accesses AWS must remain read-only and should be clearly labelled. Do not run a command that creates or updates a resource.
- If access to AWS control-plane or resources is needed beyond read-only verification, stop and ask.

### 5. CI and deployment architecture hooks
- Add an initial GitHub Actions workflow for CDK build/synth/test that uses no AWS secrets or paid runtime.
- Outline, but do not yet implement unnecessary full pipeline infrastructure, how the FastAPI BFF, React UI and AgentCore deployments will join the same gated workflow.
- Leave Render as the deployment baseline. Do not migrate hosting providers.
- Avoid blocking future AgentCore service modules by overfitting the database network pattern to Café Fausse.

## Deliverables
1. `infrastructure/` project-scoped CDK source, scripts, and documentation.
2. Infrastructure security/isolation tests and build/synth output.
3. A concise `docs/STEP1_IMPLEMENTATION_RESULTS.md` describing:
   - files added/changed and Café Fausse code reused;
   - network/MCP runtime decisions and unresolved prerequisites;
   - CDK synth results, test results, and resource summary;
   - safe deploy procedure, estimated costs and required explicit approvals;
   - schedule risk against G1 (Oct 24) and G2 (Oct 30).
4. Commit the changes to the Quantic repository on a feature branch or proposed PR where possible; do not alter the Café Fausse repository.

## Acceptance / stop gate
**Pass** only when CDK code builds/synthesizes cleanly, tests demonstrate Quantic resource isolation, no hard-coded Café resources/secrets remain, network/MCP design is justified, and a reviewer can inspect the intended AWS resources before any deployment.

**Stop for review.** No `cdk deploy`, stack creation, DB start, migration execution, NAT creation, Bedrock invocation, new IAM role creation, or paid provisioning until the user approves the exact deployment change set. Do not interpret this task as authorization to execute the build/deploy button against AWS.
