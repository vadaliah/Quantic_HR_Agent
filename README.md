# Quantic HR Agent

Agentic RAG + MCP project for Quantic AI Engineering Techniques and Architectures. **Submission: November 15, 2026.**

## Where the data lives

**Deployment = Render + the existing Aurora database.** The app runs as one Render free web
service (`render.yaml`, `Dockerfile.render`) and reads Hiren's existing Aurora Serverless v2
PostgreSQL cluster (`QuanticHrAgentStack`, database `quantic_hr_agent`) through the RDS Data
API (`DB_MODE=data_api`, read-only). Bedrock provides chat and embeddings. See
[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md). Local development and tests use a local
Postgres with the same migrations (`DB_MODE=psycopg`, the default).

| Piece | Where it runs |
| --- | --- |
| React UI (Vite) | Local (port 5173), or built into the Render service and served at `/` |
| FastAPI BFF + LangGraph + MCP | Local process, or the Render free web service (`$PORT`) |
| Database access | `DB_MODE=psycopg` locally, `DB_MODE=data_api` (Aurora Data API) on Render |
| Postgres + pgvector | Aurora Serverless v2, `us-east-2`, database `quantic_hr_agent` |
| Embeddings + chat | Amazon Bedrock: Titan Text Embeddings v2 (1024 dims) and one chat model, default Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) |

```text
Vite (5173) → FastAPI /chat /health → LangGraph → Bedrock Converse tool-use loop
                                                  ↘ stdio MCP tools → Aurora + pgvector
```

The agent runs a Bedrock Converse tool-use loop over the MCP tools and answers only from
tool results, citing `[document_id section_id]`. If no tool result grounds the answer it
abstains and points to People Operations. When Bedrock is unavailable (no AWS credentials,
an error, or `QUANTIC_AGENT_MODE=keyword`) it falls back to the local keyword router, which
uses the same MCP tools. Policy search uses pgvector cosine similarity over Titan v2
embeddings and falls back to `ILIKE` when no embeddings are loaded.

## Configuration

One chat model is used at a time. `BEDROCK_CHAT_INFERENCE_PROFILE` (app) and the CDK context
`quanticChatModel` (runtime role) must name the same model:

| Model | App setting | CDK context | Status in us-east-2 (checked 2026-11-11) |
| --- | --- | --- | --- |
| Amazon Nova Pro (default) | `us.amazon.nova-pro-v1:0` | `nova-pro` | Active via `us.` profile only; access in 287238357427 **not yet confirmed** |
| Claude Sonnet 4.6 (alternative) | `us.anthropic.claude-sonnet-4-6` | `claude-sonnet-4-6` | Active via `us.` profile; Claude access recorded in `docs/STEP0_AWS_FINDINGS.md` |

> **Before deploy:** confirm Nova Pro model access is enabled in account `287238357427`
> (us-east-2). `docs/STEP0_AWS_FINDINGS.md` records only Titan and Claude. If it is not
> enabled, enable it or switch both settings to Claude Sonnet 4.6.

Claude Sonnet 4.5 is marked Legacy in Bedrock and is no longer configured.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BEDROCK_CHAT_INFERENCE_PROFILE` | `us.amazon.nova-pro-v1:0` | Chat model (see above) |
| `BEDROCK_EMBEDDING_MODEL` | `amazon.titan-embed-text-v2:0` | Embeddings, 1024 dims, normalized |
| `AWS_REGION` | `us-east-2` | Bedrock region |
| `QUANTIC_AGENT_MODE` | `auto` | `auto` (Bedrock when AWS credentials exist), `bedrock`, `keyword` |
| `QUANTIC_RETRIEVAL` | `auto` | `auto` (vector when embeddings and credentials exist), `vector`, `keyword` |
| `QUANTIC_MIN_SIMILARITY` | `0.2` | Cosine floor for policy matches; lower matches are dropped so the agent abstains. Tune after ingestion. |
| `QUANTIC_AS_OF` | today | Fixed date for PTO balances (evaluation and tests pin `2026-11-03`) |

## Database setup

The database is named `quantic_hr_agent` everywhere: the CDK cluster default database,
the Data API migration runner, migration 003's grant, the scripts and `.env.example`.

Migrations and seeds run through the guarded RDS Data API runner. It opens its own
transaction, uses the admin secret, verifies the account, region and cluster before doing
anything, and prompts for a typed confirmation.

```bash
# 1. Parse-check offline first (no AWS call)
bash infrastructure/database/scripts/run-sql.sh --check infrastructure/database/migrations/004_hr_schema_v2.sql

# 2. Apply migrations in order
QUANTIC_ALLOW_SQL_MIGRATIONS=yes bash infrastructure/database/scripts/run-sql.sh infrastructure/database/migrations/004_hr_schema_v2.sql
QUANTIC_ALLOW_SQL_MIGRATIONS=yes bash infrastructure/database/scripts/run-sql.sh infrastructure/database/migrations/005_tighten_runtime_grants.sql

# 3. Seed synthetic HR data (25 employees, PTO accrual, benefits)
python infrastructure/database/scripts/seed.py > /tmp/quantic_seed.sql
bash infrastructure/database/scripts/run-sql.sh --check /tmp/quantic_seed.sql
QUANTIC_ALLOW_SQL_MIGRATIONS=yes bash infrastructure/database/scripts/run-sql.sh /tmp/quantic_seed.sql
```

Order matters: `005` revokes the runtime role's write access, so seeding and corpus ingestion
always use the admin secret.

## Corpus ingestion (RAG)

`corpus/` holds 12 policy documents, POL-001 to POL-012 (~5,600 words; POL-006 and POL-011
are in `corpus/sources/`). `corpus/SOURCES.md` is provenance, not a policy, and is not ingested.
Until ingestion has run, `policy_chunks` is empty and policy questions return
"no matching passage" — that is the correct answer against an empty index, not a bug.

```bash
export DATABASE_URL=postgresql://quantic_hr_admin:<pw>@<cluster-endpoint>:5432/quantic_hr_agent
uv run python scripts/ingest_corpus.py --dry-run          # parse + chunk only, no AWS, no writes
uv run python scripts/ingest_corpus.py                    # embed with Titan v2 and write policy_chunks
uv run python scripts/ingest_corpus.py --skip-embeddings  # text only (keyword search), no AWS
```

`--dry-run` reports 12 documents and 134 chunks (one per numbered section) and an estimate
of about 9,200 tokens, well under one cent of Titan v2 embedding, one time. Chunk IDs are
`<document>:<section>` (for example `POL-001:2.1`), so re-running updates rows in place;
unchanged text keeps its embedding (`content_sha`), sections removed from a document are
deleted, and `--force` re-embeds everything.

Ingestion needs a direct Postgres connection because the embeddings must be computed by
Bedrock before the SQL is written, which the Data API cannot do on its own.

## Running the app

The application needs `DATABASE_URL` and AWS credentials for Bedrock.

```bash
uv sync --group dev
export DATABASE_URL=postgresql://quantic_hr_agent@<cluster-endpoint>:5432/quantic_hr_agent
export AWS_REGION=us-east-2
uv run uvicorn quantic_hr.bff:app --app-dir src --port 8000

# in another shell
npm --prefix frontend install
npm --prefix frontend run dev
```

## Tests

```bash
uv run pytest -q
```

No test calls AWS: Bedrock is replaced by a fake client (`tests/fakes.py`). Tests that touch
the database need `DATABASE_URL` pointing at a Postgres with pgvector, migrations 001–006 and
the seed applied; they are **skipped** when it is unreachable. The policy-search tests also
need `policy_chunks` loaded (`ingest_corpus.py --skip-embeddings` is enough).

## Demo workflows

Seed employees are `E1001`–`E1025` (`mock_data/employees.json`); the UI offers E1007, E1012,
E1019 and E1001.

1. **Remote work from abroad** — `E1007` asks about working from Portugal for six weeks.
   Over 30 consecutive days triggers People Operations and Legal approval (POL-004 2.2), with
   security conditions from POL-006 3.3 and the approval path from POL-003 4.3.
2. **PTO request** — `E1012` asks about three days next week. The balance covers it
   (POL-001 2.1), three days or more needs manager approval (POL-001 3.1), and five business
   days' notice applies. `E1019` is the insufficient-balance path.

## AWS CDK (record of the existing database stack only)

```bash
cd infrastructure
npm ci && npm test && npm run synth && npm run synth:reuse
```

**Do not run `cdk deploy` from this branch.** `QuanticHrAgentStack` is already deployed in
account `287238357427`, `us-east-2` (created 2026-11-03; Aurora database `quantic_hr_agent`
holds live data, deletion protection on, pre-update snapshot
`quantic-hr-agent-pre-update-20261111-2326`). The read-only `cdk diff` of 2026-11-11
([docs/evidence/cdk-diff-2026-11-11.txt](docs/evidence/cdk-diff-2026-11-11.txt)) shows this
code would replace the DB subnets and security group. The CDK app is kept only as a record of
the database stack. The AgentCore pieces (`Dockerfile`, `/invocations`, the
`AgentContainerRuntime` construct) are not used. Do not run `scripts/deploy-sandbox.sh`.
Café Fausse and AEA stay untouched.

## Deployment and teardown

Hosting is Render; follow [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).

**Status (2026-11-12 ~00:10 CET): not live yet.** The IAM user `quantic-hr-render` with the
least-privilege policy and its access key exist. The smoke tests passed: Nova Pro Converse, Titan v2,
and Data API reads (the live DB has 25 employees and 173/173 embedded chunks). Still to do: the AWS
Budget alert, the Render Blueprint, and a live URL. Do not run `cdk deploy`.

- **AWS side:** an IAM user with `infrastructure/iam/render-app-policy.json` (Bedrock
  `InvokeModel` on Nova Pro and Titan v2, Data API on the one cluster, `GetSecretValue` on the
  one secret) and an AWS Budget alert of about $10. Humans create both; nothing else changes
  in AWS.
- **Cost:** Render free tier; Aurora stays at 0 ACU when idle (auto-pause after 300 s);
  Bedrock is pay per request.
- **Model access.** Nova Pro (the default) is confirmed in account `287238357427` (Converse
  smoke call, 2026-11-12); `CHAT_MODEL=us.anthropic.claude-sonnet-4-6` is the alternative.
- **Teardown after grading:** delete the IAM access key (or user) and suspend or delete the
  Render service. The Aurora cluster is Hiren's and stays as is.

## Docs
- [Deploy on Render](docs/DEPLOY_RENDER.md)
- [Cost-first strategy](docs/COST_FIRST_DELIVERY_STRATEGY.md)
- [Master plan](docs/MASTER_PLAN.md)
- [design-and-evaluation.md](design-and-evaluation.md)
- [ai-tooling.md](ai-tooling.md)
- [deployed.md](deployed.md)
