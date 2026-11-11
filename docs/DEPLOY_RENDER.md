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

## Open checks (not yet verified against the live database)

- The live schema and data must match what the tools query (`pto_accruals`,
  `pto_balance_as_of()`, employee IDs `E1001`-`E1025`, `policy_chunks.embedding`). Nobody has
  run a query against the live database from this branch; that is a read and needs Hiren's go.
- If `policy_chunks` has no embeddings, retrieval falls back to keyword search automatically.
  Loading embeddings is an ingest (a write) and is **not** part of this change.
- Nova Pro model access in account `287238357427` is still to be confirmed with a first call.
