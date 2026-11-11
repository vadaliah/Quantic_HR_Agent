# Deploy on Render (free tier) against the existing Aurora database

Team decision, 2026-11-11 23:30 CET: the app runs as **one Render free web service**.
AWS keeps only what already exists: Hiren's `QuanticHrAgentStack` Aurora Serverless v2
cluster (database `quantic_hr_agent`) and Amazon Bedrock. No new AWS infrastructure is
deployed for hosting.

```text
Browser → Render web service (React UI + FastAPI /chat, LangGraph tool loop, stdio MCP tools)
            │  HTTPS, signed with an IAM user access key (render-app-policy.json)
            ├─→ Bedrock Runtime us-east-2: Converse on us.amazon.nova-pro-v1:0, Titan Text Embeddings v2
            └─→ RDS Data API (rds-data) ─→ existing Aurora Serverless v2 cluster (isolated subnets)
                                           credentials from the Secrets Manager secret
```

## Current state (2026-11-12, ~00:10 CET)

**Not live yet.** There is no Render service and no URL.

| Item | State |
| --- | --- |
| IAM user `arn:aws:iam::287238357427:user/quantic-hr-render` (tags `project=quantic-hr-agent`, `purpose=render-app`, `delete-after=grading`) | ✅ Done |
| Inline policy `render-app-least-privilege` = `infrastructure/iam/render-app-policy.json` at `23f5b92` | ✅ Done |
| IAM policy simulator: `rds-data:ExecuteStatement` (cluster), `secretsmanager:GetSecretValue` (secret), `bedrock:InvokeModel` (Titan v2) **allowed**; `rds:DeleteDBCluster`, `secretsmanager:PutSecretValue`, `s3:ListAllMyBuckets` **denied** | ✅ Done |
| One access key (Active), stored outside the repo by the repo owner's collaborator; goes only into Render env (`sync: false`) | ✅ Done; rotate/delete after grading |
| Smoke with that key: STS identity = `user/quantic-hr-render`; Bedrock Converse on `us.amazon.nova-pro-v1:0` OK (**Nova Pro access confirmed** in the account); Titan v2 `InvokeModel` OK | ✅ Done |
| Data API first call returned `DatabaseResumingException` (auto-pause wake), then succeeded; the app retries for up to 60 s | ✅ Observed |
| Read-only Data API check of the live database (SELECT only, counts only; see below) | ✅ Done |
| AWS Budget alert (~US$10) | ⏳ Pending (alert email to be provided) |
| Render Blueprint created, key pasted, deployed | ⏳ Pending |
| Live URL in `deployed.md`, `/health` shows `database.ok: true`, two demo tasks checked | ⏳ Pending |

**Live database, read-only check (2026-11-12 ~00:15 CET, as `quantic-hr-render`, SELECT only):**

- Public tables: `agent_runs`, `benefits`, `employees`, `locations`, `managers`, `policy_chunks`, `policy_documents`, `pto_accruals`, `pto_balances`, `pto_blackouts`, `tickets`.
- `employees`: 25 rows, IDs `E1001`–`E1025`. `pto_accruals`: 25 rows. `pto_balance_as_of()` exists (1 row in `pg_proc`). pgvector 0.8.0.
- `policy_documents`: 16. `policy_chunks`: 173, **all 173 with an embedding**, all 1024 dimensions. This matches Titan v2, so vector retrieval works without any ingest.
- Note: the live database holds 16 documents / 173 chunks, while this branch's `corpus/` has 12 documents / 134 chunks. The live data was loaded separately; do not re-ingest from this branch without Hiren's go.

Unchanged: Hiren's `QuanticHrAgentStack` is untouched (deletion protection on, snapshot
`quantic-hr-agent-pre-update-20261111-2326`). The ECR image was deleted. There was no `cdk deploy`.

## Do NOT run `cdk deploy` from this branch

The read-only `cdk diff` of 2026-11-11 ([evidence/cdk-diff-2026-11-11.txt](evidence/cdk-diff-2026-11-11.txt))
shows this branch's CDK app would **replace both isolated DB subnets and the database security
group**, move the DB subnet group and cluster onto them, may replace the writer instance, raise
the Serverless v2 minimum from 0 to 0.5 ACU (no more auto-pause), and add a NAT gateway, an
EC2 access host and an AgentCore runtime. The CDK code is kept as a record of the existing
database stack only. The AgentCore files (`Dockerfile`, `/invocations`,
`infrastructure/lib/constructs/agent-container-runtime.ts`) are **not used**.

## What the app needs (already in `render.yaml`)

| Variable | Value |
| --- | --- |
| `AWS_REGION` | `us-east-2` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | IAM user key, set in the Render dashboard (`sync: false`) |
| `DB_MODE` | `data_api` |
| `DB_CLUSTER_ARN` | `arn:aws:rds:us-east-2:287238357427:cluster:quantichragentstack-databaseaurorapostgres6560ef93-h8yvdkzw8voy` |
| `DB_SECRET_ARN` | `arn:aws:secretsmanager:us-east-2:287238357427:secret:quantic-hr-agent/dev/database/admin-e4lGu2` |
| `DB_NAME` | `quantic_hr_agent` |
| `CHAT_MODEL` | `us.amazon.nova-pro-v1:0` (alternative `us.anthropic.claude-sonnet-4-6`) |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` |

The Data API is already enabled on the cluster (`HttpEndpointEnabled=true`). The app path is
read-only: `src/quantic_hr/db.py` refuses anything but a single `SELECT`/`WITH` statement.

## Steps the humans do

1. **IAM user and key** (account `287238357427`, someone with IAM rights):
   create a user such as `quantic-hr-render`, no console access, attach the inline policy
   [`infrastructure/iam/render-app-policy.json`](../infrastructure/iam/render-app-policy.json),
   create one access key. Do not paste the key into chat, git or docs.
2. **Budget alert:** AWS Budgets → monthly cost budget of about **$10** with an email alert at
   80 % actual and 100 % forecast.
3. **Render:** New → Blueprint → this repository and branch → it reads `render.yaml`. Enter
   `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` when prompted. Deploy, then open
   `https://<service>.onrender.com/` (UI), `/ping` and `/health`.
4. **Check before sharing:** `/health` shows `database.ok: true` and `mode: data_api`; ask the
   two demo questions in the README and confirm citations.
5. **After grading:** deactivate and delete the access key (or the whole IAM user), suspend or
   delete the Render service, and remove the budget if no longer wanted. Rotate the key
   immediately if it is ever exposed.

### Why these permissions (least privilege)

- `bedrock:InvokeModel` authorizes **Converse** as well: the Converse API reference says
  "This operation requires permission for the `bedrock:InvokeModel` action"
  ([API_runtime_Converse](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html)).
  The app does not stream, so `InvokeModelWithResponseStream` is not granted.
- Cross-Region inference needs the profile ARN **and** the foundation model in every
  destination Region. `aws bedrock get-inference-profile` from us-east-2 (read-only, 2026-11-11)
  lists us-east-1, us-east-2 and us-west-2 for `us.amazon.nova-pro-v1:0`.
- Titan v2 embeddings are called in-Region (us-east-2) on the foundation model.
- `rds-data:ExecuteStatement` / `BatchExecuteStatement` on the one cluster ARN and
  `secretsmanager:GetSecretValue` on the one secret ARN, as in the AWS minimum Data API policy
  ([data-api.access](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/data-api.access.html)).
  The secret uses the AWS-managed key, so no `kms:Decrypt` is needed. No transactions are
  used, so `BeginTransaction`/`CommitTransaction`/`RollbackTransaction` are not granted.
- Known limitation: the secret is the cluster **admin** login. The app guard is read-only,
  but the database would not stop a write made with this key. A read-only database role with
  its own secret would close that gap; it needs a DB write, so it waits for Hiren's go.

Optional Sonnet 4.6 alternative (add only if `CHAT_MODEL` switches):

```json
{
  "Sid": "ChatClaudeSonnet46ViaUsInferenceProfile",
  "Effect": "Allow",
  "Action": "bedrock:InvokeModel",
  "Resource": [
    "arn:aws:bedrock:us-east-2:287238357427:inference-profile/us.anthropic.claude-sonnet-4-6",
    "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6",
    "arn:aws:bedrock:us-east-2::foundation-model/anthropic.claude-sonnet-4-6",
    "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-sonnet-4-6"
  ]
}
```

## Cold starts

- **Render free** spins the service down after about 15 minutes without traffic; the next
  request waits for it to start (often 30-60 s).
- **Aurora** pauses after 300 s idle (Serverless v2 minimum 0 ACU). The first Data API call
  then gets `DatabaseResumingException`; the adapter retries with backoff for up to
  `DB_RESUME_WAIT_SECONDS` (60 s). The Render health check uses `/ping`, which never touches
  the database, so it does not keep Aurora awake.
- Before a demo or grading session, open `/health` once and wait for `database.ok: true`.

## Open checks

- ~~Live schema and data match the tools~~ — verified read-only on 2026-11-12 (see Current state).
- ~~Embeddings present~~ — 173/173 chunks embedded (1024-d); no ingest needed.
- ~~Nova Pro model access~~ — confirmed by a Converse smoke call on 2026-11-12.
- Still open: the end-to-end `/chat` answers and citations on the live Render URL, and measured cold-start times.
