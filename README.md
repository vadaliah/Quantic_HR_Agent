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
| Embeddings + chat | Amazon Bedrock (Titan Text Embeddings v2, Claude) |

```text
Vite (5173) → FastAPI /chat /health → LangGraph → stdio MCP → Aurora + pgvector
```

## Database setup

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

`corpus/` holds 16 policy documents (~8,200 words). Vector search runs only against Aurora.
Until ingestion has run, `policy_chunks` is empty and policy questions return
"no matching passage" — that is the correct answer against an empty index, not a bug.

```bash
export DATABASE_URL=postgresql://quantic_hr_admin:<pw>@<cluster-endpoint>:5432/quantic_hr_agent
python scripts/ingest_corpus.py --dry-run   # parse + chunk only, no AWS, no writes
python scripts/ingest_corpus.py             # embed with Titan and write policy_chunks
```

`--dry-run` reports 16 documents and 177 chunks without contacting AWS. Embedding the whole
corpus is about 9,600 tokens, roughly three cents, one time. Chunk IDs are content hashes, so
re-running overwrites rather than duplicating; `--force` re-embeds everything.

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

Tests that touch the database require `DATABASE_URL` pointing at Aurora. MCP tool-discovery
tests need no AWS contact.

## Demo workflows

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

## Docs
- [Cost-first strategy](docs/COST_FIRST_DELIVERY_STRATEGY.md)
- [Master plan](docs/MASTER_PLAN.md)
- [design-and-evaluation.md](design-and-evaluation.md)
- [ai-tooling.md](ai-tooling.md)
- [deployed.md](deployed.md)
