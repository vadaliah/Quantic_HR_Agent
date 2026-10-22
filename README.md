# Quantic HR Agent

Agentic RAG + MCP project for Quantic AI Engineering Techniques and Architectures. **Submission: November 15, 2026.**

Governing strategy: [docs/COST_FIRST_DELIVERY_STRATEGY.md](docs/COST_FIRST_DELIVERY_STRATEGY.md). The AWS CDK app is preserved under `infrastructure/` and **must not be deployed** until a paid-infra approval sets `QUANTIC_ALLOW_AWS_DEPLOY=yes`.

## Local spine (free / open source)

```text
Vite (localhost:5173) → FastAPI /chat /health → LangGraph → stdio MCP → Postgres+pgvector
```

Demos: remote-work eligibility (`E001`) and PTO guidance (`E002`).

```bash
./scripts/local-db.sh start
uv sync --group dev
export DATABASE_URL=postgresql://quantic@127.0.0.1:5433/quantic_hr
uv run pytest -q
uv run uvicorn quantic_hr.bff:app --app-dir src --port 8000
# in another shell
cd frontend && npm install && npm run dev
```

`docker compose up -d` is optional if you prefer a container instead of Homebrew Postgres.

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
