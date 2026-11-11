# Quantic HR Agent

Agentic RAG + MCP project for Quantic AI Engineering Techniques and Architectures. **Submission: November 15, 2026.**

## Where the data lives

There is **no local database**. All tables, seed data and vector search live in the deployed
Aurora Serverless v2 PostgreSQL cluster, reached through the RDS Data API for DDL/DML and a
private connection for the application. Local Postgres scripts, the local schema/seed files and
`docker-compose.yml` were removed so there is one source of truth.

| Piece | Where it runs |
| --- | --- |
| React UI (Vite) | Local (port 5173) or a static host |
| FastAPI BFF + LangGraph + MCP | Local process or a deployed service |
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

## AWS CDK (synth only)

```bash
cd infrastructure
npm ci && npm test && npm run synth && npm run synth:reuse
```

Do not run `scripts/deploy-sandbox.sh`. Café Fausse and AEA stay untouched.

## Deployment and teardown

**Nothing is deployed** (as of 2026-11-11). The target is `QuanticHrAgentStack` in account
`287238357427`, `us-east-2` (VPC with one NAT gateway, Aurora Serverless v2 with pgvector,
the runtime role, AgentCore).

- **Sponsor approval first.** No deploy without the sponsor's explicit go.
- **Time-limited exposure.** Agree the deploy and teardown dates before deploying. The stack
  costs roughly $75 a month while it is up (Aurora 0.5 ACU floor plus the NAT gateway), before
  Bedrock usage, so keep the window to the grading period.
- **Model access.** Confirm Nova Pro (the default) is enabled in account `287238357427` before
  deploying; it is not yet confirmed. To use Claude instead, deploy with
  `-c quanticChatModel=claude-sonnet-4-6` and set `BEDROCK_CHAT_INFERENCE_PROFILE` to match.
- **Agent image.** `cdk deploy` builds the repository `Dockerfile` for linux/arm64 (Docker with
  buildx/arm64 support required on the deploying machine) and pushes it to the CDK bootstrap
  repository `cdk-hnb659fds-container-assets-287238357427-us-east-2`, tagged with the asset hash.
  AgentCore Runtime then runs it (`/ping`, `/invocations` on port 8080). To build only:
  `docker buildx build --platform linux/arm64 -t quantic-hr-agent .`
  `-c quanticRuntimeImage=hello-world` deploys the Hello World runtime instead.
- **Teardown.** `cd infrastructure && npx cdk destroy QuanticHrAgentStack`. Aurora deletion
  protection is off by default (`quanticDeletionProtection=false`) so the cluster is deleted
  with no final snapshot. If it was deployed with `-c quanticDeletionProtection=true`, the
  cluster is retained: turn protection off and delete it explicitly. The runtime log group
  `/quantic-hr-agent/dev/runtime` is retained by design and the admin secret enters Secrets
  Manager's recovery window; remove or wait them out after grading. **ECR images in the
  bootstrap repository are not removed by `cdk destroy`**: delete the agent image tags from
  `cdk-hnb659fds-container-assets-287238357427-us-east-2` (or run `cdk gc` if enabled) to stop
  the small storage charge.

## Docs
- [Cost-first strategy](docs/COST_FIRST_DELIVERY_STRATEGY.md)
- [Master plan](docs/MASTER_PLAN.md)
- [design-and-evaluation.md](design-and-evaluation.md)
- [ai-tooling.md](ai-tooling.md)
- [deployed.md](deployed.md)
