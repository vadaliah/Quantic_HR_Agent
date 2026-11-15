# AI tooling

Updated: 15 November 2026 (Europe/Berlin)

This disclosure lists AI and platform tools that are evidenced in this repository.

## Development assistant

Cursor is documented in the previous version of this file as the coding assistant used against this repository, with `docs/COST_FIRST_DELIVERY_STRATEGY.md` as the governing cost-first strategy. Git history does not add a stronger independent signal: commits are authored by Hiren Vadalia; there are no `Co-authored-by` trailers or bot committers naming another coding assistant. Cursor is therefore retained as the development assistant of record because the in-repo disclosure already stated it, not because a commit trailer was found.

## Runtime and scaffolding (evidenced in the tree)

- **Amazon Bedrock** is the deployed inference and embedding path: chat defaults to Amazon Nova Pro (`us.amazon.nova-pro-v1:0`) and embeddings to Titan Text Embeddings v2 (`amazon.titan-embed-text-v2:0`), as configured in the application and documented in the README and `design-and-evaluation.md`.
- **LangGraph** orchestrates the Bedrock Converse tool-use loop and the keyword fallback (`src/quantic_hr/agent.py`).
- **Python MCP** (`mcp` / FastMCP in `src/quantic_hr/mcp_server.py`) exposes the eight tools over stdio.
- **FastAPI** is the BFF (`src/quantic_hr/bff.py`).
- **Vite / React** is the frontend (`frontend/`).
- **Postgres + pgvector** stores policy chunks and mock HR data. Local development uses a local Postgres (`DB_MODE=psycopg`). The live Render service reads the existing Aurora Serverless v2 cluster through the RDS Data API (`DB_MODE=data_api`).

## What is free locally, and what is paid in production

The previous one-line version of this file said that no paid AWS model or database calls were required for "the current spine." That was true of the earlier local-only path and is now incomplete.

- Local development and the default test suite can still run without paid AWS calls: tests stub Bedrock (`tests/fakes.py`), and `QUANTIC_AGENT_MODE=keyword` / `QUANTIC_RETRIEVAL=keyword` avoid Bedrock. Local Postgres is sufficient for the skipped-in-CI tests once it is seeded.
- The **deployed** service does use paid AWS resources: Bedrock (pay per request) and Hiren's existing Aurora Serverless v2 cluster (auto-pause when idle). This documentation update does not create, change, or call those resources, and it does not call live `/chat`.

## What did not work well

- An evaluation scorer bug dropped the section marker from gold document IDs (`POL-001 2.1` → `pol-0012.1`) while tool citations normalised to `pol-001s2.1`, so a 30-case run committed as citation accuracy 0.0 even when the correct section was cited. That helper is corrected in this change; the traces were re-scored offline and were not re-run against `/chat`.
- Database-backed tests, including MCP discovery, skip in GitHub Actions because CI has no seeded Postgres. The offline suite still passes.
- Deploying from this branch is not gated on CI: Render has been observed to start a deploy on push before tests finish.

## Academic integrity

AI assistance was used during development. The author remains responsible for the submitted implementation, its correctness, cost controls, evaluation, and documentation. All employee examples and HR records used by the demonstration are synthetic. Café Fausse and AEA are out of scope and untouched.
